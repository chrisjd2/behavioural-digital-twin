import json
from collections.abc import Mapping
from pathlib import Path

from backend.arms import (
    ARM_C_SYSTEM,
    ARM_SPECS,
    ArmResources,
    LLMOptions,
    distil_profile,
    prompt_hashes,
)
from backend.data import DataSource, NewsItem, build_candidate_set
from backend.experiment import ExperimentConfig
from backend.llm import Cache, LLMClient, RawResponse, mock_backend
from backend.profiles import (
    PROFILE_CLICKS,
    PROFILE_SYSTEM,
    parse_profile,
    profile_block,
    profile_history,
    profile_messages,
)
from backend.runner import run_experiment
from tests.factories import make_impression

OPTIONS = LLMOptions("medium", 4096, base_rate_hint=False)
HISTORY = [f"H{i}" for i in range(60)]
NEWS = {i: NewsItem(i, "sports", "nfl", f"Headline {i}", "") for i in HISTORY}


def profile_json(**fields: list[dict[str, object]]) -> str:
    empty = {"interests": [], "rarely_clicks": [], "style_preferences": [], "recent_shifts": []}
    return json.dumps({**empty, **fields})


def test_profile_prompt_bans_identity_inference_and_uses_last_50_clicks() -> None:
    messages = profile_messages(HISTORY, NEWS)

    for banned in (
        "demographics (age, gender, location",
        "personality, political or religious affiliation, health status or",
        "sexuality",
    ):
        assert banned in PROFILE_SYSTEM
    listing = messages[1]["content"]
    assert '"H10"' in listing
    assert '"H9"' not in listing  # only the last PROFILE_CLICKS
    assert PROFILE_CLICKS == 50


def test_items_must_cite_real_clicks() -> None:
    content = profile_json(
        interests=[
            {"text": "NFL coverage", "evidence": ["H59", "H58"]},
            {"text": "Invented", "evidence": ["N999"]},
            {"text": "Uncited", "evidence": []},
        ]
    )

    profile = parse_profile(content, HISTORY)

    assert profile.fields["interests"] == [{"text": "NFL coverage", "evidence": ["H59", "H58"]}]
    assert profile.dropped_items == 2
    assert profile.ok


def test_evidence_outside_the_last_50_clicks_is_not_allowed() -> None:
    profile = parse_profile(profile_json(interests=[{"text": "Old", "evidence": ["H0"]}]), HISTORY)

    assert profile.dropped_items == 1
    assert not profile.ok  # nothing usable left


def test_over_120_words_is_not_ok() -> None:
    long_text = " ".join(["word"] * 121)
    profile = parse_profile(
        profile_json(interests=[{"text": long_text, "evidence": ["H59"]}]), HISTORY
    )

    assert profile.word_count == 121
    assert not profile.ok


def test_planted_identity_hit_is_flagged_not_blocked() -> None:
    content = profile_json(
        interests=[{"text": "Is a liberal who follows climate news", "evidence": ["H59"]}]
    )

    profile = parse_profile(content, HISTORY)

    assert profile.ok
    assert [hit["kind"] for hit in profile.identity_hits] == ["politics"]


def test_agent_sees_profile_text_not_evidence_ids() -> None:
    block = profile_block({"interests": [{"text": "NFL coverage", "evidence": ["H59"]}]})

    assert block == "Interests: NFL coverage"


def client_with(backend: object, tmp_path: Path) -> LLMClient:
    return LLMClient(
        model="m",
        base_url="u",
        cache=Cache(tmp_path / "c.sqlite"),
        backend=backend,  # type: ignore[arg-type]
        concurrency=2,
    )


async def test_profile_is_retried_once_then_cached(tmp_path: Path) -> None:
    replies = ["not json", profile_json(interests=[{"text": "NFL", "evidence": ["H59"]}])]
    calls: list[Mapping[str, object]] = []

    async def backend(payload: Mapping[str, object]) -> RawResponse:
        calls.append(payload)
        return RawResponse(replies[min(len(calls) - 1, 1)], 0, 0)

    resources = ArmResources(client=client_with(backend, tmp_path), options=OPTIONS, news=NEWS)

    first = await distil_profile(HISTORY, resources)
    second = await distil_profile(HISTORY, resources)

    assert first == second
    assert first.ok
    assert len(calls) == 2  # one attempt + one retry, then both cached


def test_profile_request_is_in_the_prompt_hashes() -> None:
    hashes = prompt_hashes(OPTIONS)

    assert {"A", "C", "D", "profile"} <= set(hashes)
    assert (
        hashes["profile"]
        != prompt_hashes(LLMOptions("high", 4096, base_rate_hint=False))["profile"]
    )


def test_arm_d_prompt_has_profile_and_memories() -> None:
    candidates = build_candidate_set(make_impression(), seed=1, max_candidates=8, max_clicked=2)
    news = {i: NewsItem(i, "sports", "nfl", f"Headline {i}", "") for i in candidates.items}
    knowledge = {
        "profile": {
            "ok": True,
            "fields": {"interests": [{"text": "NFL coverage", "evidence": ["H1"]}]},
        },
        "memories": [{"news_id": "H1", "headline": "Old click", "category": "sports"}],
    }

    d = ARM_SPECS["D"].render(candidates, news, knowledge, base_rate_hint=False)
    c = ARM_SPECS["C"].render(candidates, news, knowledge, base_rate_hint=False)

    system = d[0]["content"]
    assert "Interests: NFL coverage" in system
    assert "- [sports] Old click" in system
    assert "H1" not in system
    assert system.startswith(ARM_C_SYSTEM)  # D is C plus one sentence and the profile
    assert d[1] == c[1]


def test_an_unusable_profile_is_never_shown() -> None:
    candidates = build_candidate_set(make_impression(), seed=1, max_candidates=8, max_clicked=2)
    news = {i: NewsItem(i, "sports", "nfl", f"Headline {i}", "") for i in candidates.items}
    knowledge = {
        "profile": {
            "ok": False,
            "fields": {"interests": [{"text": "Too long", "evidence": ["H1"]}]},
        },
        "memories": [{"news_id": "H1", "headline": "Old click", "category": "sports"}],
    }

    d = ARM_SPECS["D"].render(candidates, news, knowledge, base_rate_hint=False)
    c = ARM_SPECS["C"].render(candidates, news, knowledge, base_rate_hint=False)

    assert d == c


def test_profile_never_sees_the_headlines_being_predicted() -> None:
    history = ["H1", "C0", "H2"]

    assert profile_history(history, ["C0", "C1"]) == ["H1", "H2"]
    assert (
        '"C0"'
        not in profile_messages(
            profile_history(history, ["C0"]),
            NEWS | {"C0": NewsItem("C0", "sports", "nfl", "Candidate", "")},
        )[1]["content"]
    )


def test_malformed_evidence_is_dropped_not_fatal() -> None:
    content = profile_json(interests=[{"text": "NFL", "evidence": [["H59"], 7, "H58"]}])

    assert parse_profile(content, HISTORY).fields["interests"] == [
        {"text": "NFL", "evidence": ["H58"]}
    ]


async def test_the_better_attempt_is_kept_when_neither_is_usable(tmp_path: Path) -> None:
    long_text = " ".join(["word"] * 130)
    replies = [profile_json(interests=[{"text": long_text, "evidence": ["H59"]}]), "not json"]
    calls: list[Mapping[str, object]] = []

    async def backend(payload: Mapping[str, object]) -> RawResponse:
        calls.append(payload)
        return RawResponse(replies[len(calls) - 1], 0, 0)

    resources = ArmResources(client=client_with(backend, tmp_path), options=OPTIONS, news=NEWS)

    profile = await distil_profile(HISTORY, resources)

    assert not profile.ok
    assert profile.word_count == 130  # the first attempt, not the empty second one


async def test_arm_d_runs_and_reports_the_identity_screen(
    sample_source: DataSource, tmp_path: Path
) -> None:
    client = LLMClient(
        model="mock",
        base_url="mock://",
        cache=Cache(tmp_path / "c.sqlite"),
        backend=mock_backend,
        concurrency=4,
    )

    run = await run_experiment(
        sample_source,
        ExperimentConfig(n_dev=10, n_test=20),
        population="dev",
        arms=["D"],
        client=client,
        options=OPTIONS,
    )

    users = [u for u in run.users if u.arm == "D"]
    assert len(users) == 10
    assert all(u.knowledge["profile"]["ok"] for u in users)  # type: ignore[index]
    assert all(u.knowledge["memories"] for u in users)
    assert run.identity_screen["D"] == {
        "profiles": 10,
        "flagged_profiles": 0,
        "hits": 0,
        "unusable_profiles": 0,
        "dropped_items": 0,
    }
