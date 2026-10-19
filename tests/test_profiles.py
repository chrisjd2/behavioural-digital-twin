import json
from collections.abc import Mapping
from pathlib import Path

import pytest

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
    identity_screen,
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


# Phrasings from the PR #37 experiment review (74 adversarial cases, condensed): claims,
# fragments, verbs and age forms, in the style real profiles are written.
SHOULD_FLAG = {
    "politics": [
        "The reader is a conservative who follows politics",
        "Conservative-leaning reader",
        "Politically liberal",
        "Leans left",
        "Votes Republican",
        "Supports Democrats",
        "Likely a progressive voter",
    ],
    "religion": ["Is a devout Christian", "Religious reader", "Probably a practising Catholic"],
    "gender": ["Likely a mother of young children", "Presumably female", "Female reader"],
    "family": ["Has young kids", "Single mother", "Is married", "Is likely a grandmother"],
    "age": [
        "Probably retired, reads in the morning",
        "in their 30s, follows markets",
        "in his early 40s",
        "Over 60",
        "65+",
        "Gen Z",
        "Approaching retirement",
        "Is a college student",
    ],
    "health": [
        "Possibly pregnant given baby stories",
        "living with diabetes",
        "Diabetic reader",
        "Struggles with weight",
        "Suffers from anxiety",
        "Recovering alcoholic",
    ],
    "location": ["Likely lives in Minnesota", "Based in California", "Probably from Minneapolis"],
    "occupation": ["Is a nurse", "Works as a teacher", "Likely a veteran", "Works in finance"],
    "personality": ["Introverted", "Neurotic reader", "Anxious personality", "Outgoing person"],
    "income": ["Affluent household", "Is probably wealthy", "Working-class reader"],
    "ethnicity": ["Is likely Hispanic", "Asian American reader"],
    "sexuality": ["Probably gay", "LGBTQ reader"],
}


@pytest.mark.parametrize(
    ("text", "kind"), [(text, kind) for kind, texts in SHOULD_FLAG.items() for text in texts]
)
def test_identity_screen_flags_claims_about_the_person(text: str, kind: str) -> None:
    assert kind in {hit["kind"] for hit in identity_screen(text)}


@pytest.mark.parametrize(
    "text",
    [
        "Follows Black Friday deals and White House coverage",
        "Reads about the Republican primary and Democratic debates",
        "Clicks women's soccer and health news",
        "Interested in retirement planning and religion stories",
        "Follows stories as a father and son reunite",
        "Clicks deals being Black Friday",
        "Prefers straight news and explainers",
        "A 40-year-old record broken in athletics",
        "Follows royal family updates",
        "Clicks celebrity weddings and divorces",
        "Reads news from Washington and Minnesota",
        "Clicks diabetes research and cancer breakthroughs",
        "Follows teenager sports results",
        "Personal finance and markets",
        "Nurses' strike coverage",
    ],
)
def test_identity_screen_ignores_news_topics(text: str) -> None:
    assert identity_screen(text) == []


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
