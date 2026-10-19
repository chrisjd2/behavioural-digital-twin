import json

from backend.arms import (
    OUTPUT_SCHEMA,
    arm_a_messages,
    parse_reactions,
    prompt_hashes,
    request_payload,
)
from backend.data import NewsItem, build_candidate_set
from tests.factories import make_impression

CANDIDATES = build_candidate_set(make_impression(), seed=1, max_candidates=8, max_clicked=2)
NEWS = {
    news_id: NewsItem(news_id, "sports", "nfl", f"Headline {news_id}", f"Abstract {news_id}")
    for news_id in CANDIDATES.items
}


def user_content(messages: list[dict[str, str]]) -> str:
    return next(m["content"] for m in messages if m["role"] == "user")


def test_arm_a_uses_feed_framing_and_lists_headlines_in_display_order() -> None:
    messages = arm_a_messages(CANDIDATES, NEWS, base_rate_hint=False)

    system = messages[0]["content"]
    user = user_content(messages)
    assert "typical Microsoft News reader" in system
    assert "appeared in your Microsoft News feed" in user
    assert "among many others" in user
    positions = [user.index(f"Headline {i}") for i in CANDIDATES.items]
    assert positions == sorted(positions)


def test_arm_a_never_leaks_labels() -> None:
    user = user_content(arm_a_messages(CANDIDATES, NEWS, base_rate_hint=False))

    assert 'clicked": 1' not in user
    assert "label" not in user.lower()


def test_base_rate_hint_only_when_enabled() -> None:
    without = user_content(arm_a_messages(CANDIDATES, NEWS, base_rate_hint=False))
    with_hint = user_content(arm_a_messages(CANDIDATES, NEWS, base_rate_hint=True))

    assert "%" not in without
    assert "%" in with_hint


def test_request_payload_is_temperature_zero_json_schema() -> None:
    payload = request_payload(arm_a_messages(CANDIDATES, NEWS, base_rate_hint=False))

    assert payload["temperature"] == 0
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "reactions", "schema": OUTPUT_SCHEMA, "strict": True},
    }


def test_parse_valid_reactions() -> None:
    content = json.dumps(
        {
            "reactions": [
                {"id": i, "reaction": "I'd read that.", "p_click": 40} for i in CANDIDATES.items
            ]
        }
    )

    result = parse_reactions(content, CANDIDATES.items)

    assert result.ok
    assert result.p_click == dict.fromkeys(CANDIDATES.items, 40.0)
    assert result.missing == ()


def test_parse_missing_ids_and_bad_values_score_zero_and_are_counted() -> None:
    first, second, *rest = CANDIDATES.items
    content = json.dumps(
        {
            "reactions": [
                {"id": first, "reaction": "Yes.", "p_click": 70},
                {"id": second, "reaction": "Hmm.", "p_click": "lots"},
                {"id": "N999", "reaction": "Not shown.", "p_click": 90},
            ]
        }
    )

    result = parse_reactions(content, CANDIDATES.items)

    assert not result.ok
    assert result.p_click[first] == 70.0
    assert result.p_click[second] == 0.0
    assert set(result.missing) == {second, *rest}
    assert "N999" not in result.p_click


def test_parse_clamps_out_of_range_probabilities() -> None:
    (only, *_) = CANDIDATES.items
    content = json.dumps({"reactions": [{"id": only, "reaction": "!", "p_click": 140}]})

    assert parse_reactions(content, (only,)).p_click[only] == 100.0


def test_unparseable_output_scores_everything_zero() -> None:
    result = parse_reactions("not json at all", CANDIDATES.items)

    assert not result.ok
    assert set(result.p_click.values()) == {0.0}
    assert set(result.missing) == set(CANDIDATES.items)


def test_prompt_hashes_are_stable_per_arm() -> None:
    assert prompt_hashes() == prompt_hashes()
    assert set(prompt_hashes()) >= {"A"}
