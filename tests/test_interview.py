"""Step 5 Interview: guardrailed system prompts, rate limits and the recorded fallback (#21)."""

import json
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import interview
from backend.config import Settings
from backend.data import load_news
from backend.interview import (
    IDENTITY_RULE,
    REFUSAL,
    RateLimiter,
    interview_system_prompt,
)
from backend.llm import RawResponse, TransientError
from backend.runner import Run, UserResult
from backend.runs import RUNS_SUBDIR, save_run
from backend.sample import write_synthetic_sample
from tests.test_api_runs import ARMS, make_run
from tests.test_status import make_client


def make_lab(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Run]:
    """A data dir with the synthetic sample and one saved mock run of every arm."""
    directory = tmp_path_factory.mktemp("interview-lab")
    write_synthetic_sample(directory / "sample", n_users=400, n_news=300, seed=1)
    run = make_run(directory, ARMS)
    save_run(run, directory / RUNS_SUBDIR)
    return directory, run


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Run]:
    return make_lab(tmp_path_factory)


def knowledge(run: Run, arm: str, user_id: str | None = None) -> Mapping[str, object]:
    user_id = user_id or run.users[0].user_id
    return next(u.knowledge for u in run.users if u.user_id == user_id and u.arm == arm)


def result(run: Run, arm: str) -> UserResult:
    return next(u for u in run.users if u.arm == arm)


def ask(lab: tuple[Path, Run], **settings: object) -> TestClient:
    return make_client(data_dir=str(lab[0]), **settings)


def body(run: Run, arm: str = "D", text: str = "What do you like to read?") -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "user_id": run.users[0].user_id,
        "arm": arm,
        "messages": [{"role": "interviewer", "text": text}],
    }


# System prompt per arm (ADR-0007)


@pytest.mark.parametrize("arm", ["A", "B", "C", "D", "E"])
def test_every_prompt_carries_the_guardrails(lab: tuple[Path, Run], arm: str) -> None:
    prompt = interview_system_prompt(arm, knowledge(lab[1], arm))

    assert "Talk only about news interests and reading habits" in prompt
    assert IDENTITY_RULE in prompt
    assert REFUSAL in prompt


@pytest.mark.parametrize("arm", ["A", "B", "C", "D", "E"])
def test_prompts_never_hold_labels_scores_or_the_candidates(
    lab: tuple[Path, Run], arm: str
) -> None:
    run = lab[1]
    user = result(run, arm)
    prompt = interview_system_prompt(arm, user.knowledge)

    news = load_news(lab[0] / "sample" / "dev" / "news.tsv")
    for news_id in user.items:  # the headlines being predicted, clicked or not
        assert not re.search(rf"\b{news_id}\b", prompt)
        if news_id not in user.history:  # a past click may share a headline's text
            assert news[news_id].title not in prompt
    assert "p_click" not in prompt
    assert "label" not in prompt.lower()
    assert "similar to" not in prompt  # retrieval reasons quote candidate headlines


def test_arm_a_knows_only_that_it_is_a_typical_reader(lab: tuple[Path, Run]) -> None:
    prompt = interview_system_prompt("A", {})

    assert "typical Microsoft News reader" in prompt
    assert not re.search(r"\[N\d+\]", prompt.replace("[N12345]", ""))


def test_arm_b_states_the_character_is_invented(lab: tuple[Path, Run]) -> None:
    persona = knowledge(lab[1], "B")
    prompt = interview_system_prompt("B", persona)

    assert "invented" in prompt
    assert "not a real" in prompt
    assert str(persona["name"]) in prompt


def test_arm_c_cites_its_memories_by_id(lab: tuple[Path, Run]) -> None:
    memories = knowledge(lab[1], "C")["memories"]
    assert isinstance(memories, list)
    prompt = interview_system_prompt("C", knowledge(lab[1], "C"))

    for m in memories:
        assert f"[{m['news_id']}]" in prompt
        assert m["headline"] in prompt
    assert "profile" not in prompt.lower()


def test_arm_d_adds_the_profile_with_its_evidence(lab: tuple[Path, Run]) -> None:
    known = knowledge(lab[1], "D")
    profile = known["profile"]
    assert isinstance(profile, dict)
    assert profile["ok"]
    prompt = interview_system_prompt("D", known)

    interests = profile["fields"]["interests"]
    assert interests[0]["text"] in prompt
    assert all(f"[{e}]" in prompt for e in interests[0]["evidence"])
    assert "another reader" not in prompt


def test_an_unusable_profile_is_never_shown(lab: tuple[Path, Run]) -> None:
    known = dict(knowledge(lab[1], "D"))
    profile = known["profile"]
    assert isinstance(profile, dict)
    known["profile"] = {**profile, "ok": False}

    assert "MOCK interest" not in interview_system_prompt("D", known)


def test_arm_e_says_the_data_is_another_readers(lab: tuple[Path, Run]) -> None:
    prompt = interview_system_prompt("E", knowledge(lab[1], "E"))

    assert "another reader" in prompt
    assert "wrong twin" in prompt


# POST /api/interview


def test_interview_replies_in_mock_mode_with_cited_clicks(lab: tuple[Path, Run]) -> None:
    run = lab[1]
    response = ask(lab).post("/api/interview", json=body(run, "C"))

    assert response.status_code == 200
    reply = response.json()
    assert reply["mock"] is True
    assert reply["text"].startswith("MOCK")
    memories = knowledge(run, "C")["memories"]
    assert isinstance(memories, list)
    assert [c["news_id"] for c in reply["cited"]] == [m["news_id"] for m in memories[:2]]
    assert all(c["title"] for c in reply["cited"])


def test_identity_question_goes_through_the_guardrailed_prompt(
    lab: tuple[Path, Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Mapping[str, object]] = []
    original = interview.mock_interview_backend

    async def spy(payload: Mapping[str, object]) -> RawResponse:
        sent.append(payload)
        return await original(payload)

    monkeypatch.setattr(interview, "mock_interview_backend", spy)
    response = ask(lab).post("/api/interview", json=body(lab[1], "D", "How old are you?"))

    assert response.status_code == 200
    assert response.json()["text"] == f"MOCK reply. {REFUSAL}"
    assert response.json()["cited"] == []
    messages = sent[0]["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert IDENTITY_RULE in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "How old are you?"}
    assert sent[0]["temperature"] == 0


def test_the_conversation_is_sent_in_order(
    lab: tuple[Path, Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Mapping[str, object]] = []

    async def spy(payload: Mapping[str, object]) -> RawResponse:
        sent.append(payload)
        return RawResponse("Sports, mostly.", 0, 0)

    monkeypatch.setattr(interview, "mock_interview_backend", spy)
    request = body(lab[1])
    request["messages"] = [
        {"role": "interviewer", "text": "Hi"},
        {"role": "agent", "text": "Hello"},
        {"role": "interviewer", "text": "What next?"},
    ]
    ask(lab).post("/api/interview", json=request)

    assert sent[0]["messages"][1:] == [  # pyright: ignore[reportIndexIssue]
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "What next?"},
    ]


def test_the_last_message_must_be_the_interviewers(lab: tuple[Path, Run]) -> None:
    request = body(lab[1])
    request["messages"] = [{"role": "agent", "text": "Hello"}]

    response = ask(lab).post("/api/interview", json=request)

    assert response.status_code == 422
    assert response.json()["code"] == "no_question"


def test_long_agent_replies_can_be_sent_back_but_questions_are_capped(
    lab: tuple[Path, Run],
) -> None:
    request = body(lab[1])
    request["messages"] = [
        {"role": "interviewer", "text": "Hi"},
        {"role": "agent", "text": "x" * 5000},
        {"role": "interviewer", "text": "More?"},
    ]
    client = ask(lab)

    assert client.post("/api/interview", json=request).status_code == 200
    too_long = {**body(lab[1]), "messages": [{"role": "interviewer", "text": "x" * 1001}]}
    assert client.post("/api/interview", json=too_long).status_code == 422


@pytest.mark.parametrize(
    ("change", "code"),
    [({"run_id": "nope"}, "run_not_found"), ({"user_id": "U-nobody"}, "agent_not_found")],
)
def test_unknown_run_or_reader_is_404(
    lab: tuple[Path, Run], change: dict[str, str], code: str
) -> None:
    response = ask(lab).post("/api/interview", json={**body(lab[1]), **change})

    assert response.status_code == 404
    assert response.json()["code"] == code


def test_a_baseline_cannot_be_interviewed(lab: tuple[Path, Run]) -> None:
    response = ask(lab).post("/api/interview", json=body(lab[1], "random"))

    assert response.status_code == 404
    assert response.json()["code"] == "arm_not_in_run"


def test_a_failed_llm_call_is_an_error_not_an_empty_reply(
    lab: tuple[Path, Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def down(_: Mapping[str, object]) -> RawResponse:
        raise TransientError("503")

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr(interview, "mock_interview_backend", down)
    monkeypatch.setattr(interview, "retry_sleep", no_wait)
    response = ask(lab).post("/api/interview", json=body(lab[1]))

    assert response.status_code == 502
    assert response.json()["code"] == "interview_unavailable"


def test_an_empty_reply_is_an_error(lab: tuple[Path, Run], monkeypatch: pytest.MonkeyPatch) -> None:
    async def blank(_: Mapping[str, object]) -> RawResponse:
        return RawResponse("  ", 0, 0)

    monkeypatch.setattr(interview, "mock_interview_backend", blank)
    response = ask(lab).post("/api/interview", json=body(lab[1]))

    assert response.status_code == 502


@pytest.mark.parametrize("demo_mode", [False, True])
def test_the_interview_works_in_both_modes(lab: tuple[Path, Run], demo_mode: bool) -> None:
    response = ask(lab, demo_mode=demo_mode).post("/api/interview", json=body(lab[1]))

    assert response.status_code == 200


def test_real_mode_without_a_key_is_an_error_not_a_crash(lab: tuple[Path, Run]) -> None:
    client = ask(lab, mock_llm=False, llm_api_key="")

    assert client.get("/api/status").status_code == 200
    response = client.post("/api/interview", json=body(lab[1]))
    assert response.status_code == 502
    assert response.json()["code"] == "interview_unavailable"


# Rate limits (ADR-0011)


class FakeClock:
    def __init__(self, at: float = 1_000_000.0) -> None:
        self.at = at

    def __call__(self) -> float:
        return self.at


def test_per_ip_limit_is_a_sliding_hour() -> None:
    start = 1_000_000.0
    clock = FakeClock(start)
    limiter = RateLimiter(per_ip=30, daily=500, clock=clock)

    for _ in range(30):
        assert limiter.allow("1.1.1.1") is None
        clock.at += 60
    assert limiter.allow("1.1.1.1") == "ip"
    assert limiter.allow("2.2.2.2") is None  # another address is unaffected
    clock.at = start + 3_599  # the first message is not yet an hour old
    assert limiter.allow("1.1.1.1") == "ip"
    clock.at = start + 3_600
    assert limiter.allow("1.1.1.1") is None
    assert limiter.allow("1.1.1.1") == "ip"  # only the oldest message has expired


def test_daily_limit_is_global_and_resets_at_midnight_utc() -> None:
    clock = FakeClock(at=86_400 * 20_000 + 3_600)
    limiter = RateLimiter(per_ip=30, daily=500, clock=clock)

    for n in range(500):
        assert limiter.allow(f"10.0.{n // 250}.{n % 250}") is None
    assert limiter.allow("9.9.9.9") == "daily"
    clock.at = 86_400 * 20_001  # the next UTC day
    assert limiter.allow("9.9.9.9") is None


def test_quiet_addresses_are_forgotten_each_day() -> None:
    clock = FakeClock(at=86_400 * 20_000)
    limiter = RateLimiter(per_ip=30, daily=500, clock=clock)
    limiter.allow("old")
    clock.at = 86_400 * 20_001 + 10

    limiter.allow("new")

    assert set(limiter._recent) == {"new"}  # pyright: ignore[reportPrivateUsage]


def test_refused_messages_do_not_count() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_ip=1, daily=2, clock=clock)

    assert limiter.allow("a") is None
    assert limiter.allow("a") == "ip"
    assert limiter.allow("b") is None  # the refused message did not use the daily budget


def test_the_api_returns_429_past_the_per_ip_limit(lab: tuple[Path, Run]) -> None:
    client = ask(lab, interview_ip_limit_per_hour=2)

    codes = [client.post("/api/interview", json=body(lab[1])).status_code for _ in range(3)]
    other = client.post("/api/interview", json=body(lab[1]), headers={"X-Forwarded-For": "5.6.7.8"})

    assert codes == [200, 200, 429]
    assert other.status_code == 200


def test_the_api_returns_429_past_the_daily_limit(lab: tuple[Path, Run]) -> None:
    client = ask(lab, interview_daily_limit=2)

    codes = [
        client.post(
            "/api/interview", json=body(lab[1]), headers={"X-Forwarded-For": f"1.2.3.{n}"}
        ).status_code
        for n in range(3)
    ]

    assert codes == [200, 200, 429]
    assert "day" in client.post("/api/interview", json=body(lab[1])).json()["detail"]


def test_client_address_is_the_last_forwarded_hop() -> None:
    assert interview.client_address("spoofed, 203.0.113.9", "10.0.0.1") == "203.0.113.9"
    assert interview.client_address(None, "10.0.0.1") == "10.0.0.1"
    assert interview.client_address(None, None) == "unknown"


def test_default_limits_are_the_adr_ones() -> None:
    settings = Settings()

    assert (settings.interview_ip_limit_per_hour, settings.interview_daily_limit) == (30, 500)


# GET /api/interview/recorded (ADR-0008)


def write_recorded(path: Path, run: Run, **changes: object) -> Path:
    user = result(run, "C")
    memory = knowledge(run, "C", user.user_id)["memories"][0]  # pyright: ignore[reportIndexIssue]
    recorded = {
        "run_id": run.run_id,
        "user_id": user.user_id,
        "arm": "C",
        "model": "gemini-test-001",
        "mock": False,
        "exchanges": [
            {"question": "What do you read?", "answer": f"Mostly this [{memory['news_id']}]."},
            {"question": "How old are you?", "answer": REFUSAL},
        ],
        **changes,
    }
    path.write_text(json.dumps(recorded), encoding="utf-8")
    return path


def test_recorded_exchanges_are_served_with_their_citations(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    run = lab[1]
    path = write_recorded(tmp_path / "recorded.json", run)

    response = ask(lab, interview_recorded=str(path)).get("/api/interview/recorded")

    assert response.status_code == 200
    recorded = response.json()
    assert (recorded["arm"], recorded["mock"]) == ("C", False)
    assert [e["question"] for e in recorded["exchanges"]] == [
        "What do you read?",
        "How old are you?",
    ]
    assert len(recorded["exchanges"][0]["cited"]) == 1
    assert recorded["exchanges"][0]["cited"][0]["title"]
    assert recorded["exchanges"][1]["cited"] == []


def test_recorded_is_available_in_demo_mode_and_past_the_limits(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    path = write_recorded(tmp_path / "recorded.json", lab[1])
    client = ask(lab, interview_recorded=str(path), demo_mode=True, interview_daily_limit=1)
    client.post("/api/interview", json=body(lab[1]))

    assert client.post("/api/interview", json=body(lab[1])).status_code == 429
    assert client.get("/api/interview/recorded").status_code == 200


def test_missing_recording_is_an_error(lab: tuple[Path, Run], tmp_path: Path) -> None:
    response = ask(lab, interview_recorded=str(tmp_path / "none.json")).get(
        "/api/interview/recorded"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "interview_not_recorded"


def test_malformed_recording_is_an_error(lab: tuple[Path, Run], tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"run_id": 1}', encoding="utf-8")

    response = ask(lab, interview_recorded=str(path)).get("/api/interview/recorded")

    assert response.status_code == 422
    assert response.json()["code"] == "interview_recording_invalid"
