"""Prompt builders and output parsing for the LLM arms (ADR-0003, ADR-0005).

Every arm shares the output format, the feed framing and the display order;
only the system prompt (what the agent knows) differs.
"""

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from backend.data import CandidateSet, NewsItem

ABSTRACT_CHARS = 300

OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "reactions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "reaction": {"type": "string"},
                    "p_click": {"type": "number"},
                },
                "required": ["id", "reaction", "p_click"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["reactions"],
    "additionalProperties": False,
}

ARM_A_SYSTEM = (
    "You are a typical Microsoft News reader. You have no other information about yourself. "
    "Answer as that reader would, honestly and briefly."
)

# The first two sentences are ADR-0005's feed framing, verbatim.
FEED_INSTRUCTIONS = (
    "Each of these headlines appeared in your Microsoft News feed while you were browsing, "
    "among many others. For each, give your honest one-sentence gut reaction, then the "
    "probability (0-100) that you clicked it.\n"
    "Write each reaction in the first person. "
    'Reply with JSON only: {"reactions": [{"id": ..., "reaction": ..., "p_click": ...}]}, '
    "one entry per headline id."
)

BASE_RATE_HINT = "For context: readers click only about 4% of the headlines in their feed."

RETRY_INSTRUCTION = (
    "Your previous reply was not valid. Return valid JSON only, with exactly one entry for "
    "every headline id listed."
)


@dataclass(frozen=True)
class LLMOptions:
    """Request settings that change predictions; part of the frozen fingerprint (ADR-0001)."""

    reasoning_effort: str  # Gemini accepts none | low | medium | high
    max_output_tokens: int
    base_rate_hint: bool


@dataclass(frozen=True)
class ParsedReactions:
    p_click: dict[str, float]  # 0-100, every candidate present (0 when missing)
    reactions: dict[str, str]
    missing: tuple[str, ...]  # candidates with no usable p_click

    @property
    def ok(self) -> bool:
        return not self.missing


def headlines_block(candidates: CandidateSet, news: Mapping[str, NewsItem]) -> str:
    items = [
        {
            "id": news_id,
            "category": f"{news[news_id].category}/{news[news_id].subcategory}",
            "headline": news[news_id].title,
            "abstract": news[news_id].abstract[:ABSTRACT_CHARS],
        }
        for news_id in candidates.items
    ]
    return json.dumps(items, indent=1, ensure_ascii=False)


def feed_message(
    candidates: CandidateSet, news: Mapping[str, NewsItem], *, base_rate_hint: bool
) -> str:
    hint = f"{BASE_RATE_HINT}\n" if base_rate_hint else ""
    return f"{FEED_INSTRUCTIONS}\n{hint}\nHeadlines:\n{headlines_block(candidates, news)}"


def arm_a_messages(
    candidates: CandidateSet, news: Mapping[str, NewsItem], *, base_rate_hint: bool
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": ARM_A_SYSTEM},
        {"role": "user", "content": feed_message(candidates, news, base_rate_hint=base_rate_hint)},
    ]


def retry_messages(messages: list[dict[str, str]], previous: str) -> list[dict[str, str]]:
    return [
        *messages,
        {"role": "assistant", "content": previous},
        {"role": "user", "content": RETRY_INSTRUCTION},
    ]


def request_payload(messages: list[dict[str, str]], options: LLMOptions) -> dict[str, object]:
    return {
        "messages": messages,
        "temperature": 0,
        "reasoning_effort": options.reasoning_effort,
        "max_tokens": options.max_output_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "reactions", "schema": OUTPUT_SCHEMA, "strict": True},
        },
    }


def parse_reactions(content: str, ids: Sequence[str]) -> ParsedReactions:
    p_click: dict[str, float] = dict.fromkeys(ids, 0.0)
    reactions: dict[str, str] = dict.fromkeys(ids, "")
    valid: set[str] = set()
    try:
        entries = json.loads(content)["reactions"]
    except (json.JSONDecodeError, KeyError, TypeError):
        entries = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("id") not in p_click:
            continue
        news_id = entry["id"]
        reactions[news_id] = str(entry.get("reaction", ""))
        value = entry.get("p_click")
        if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
            p_click[news_id] = min(max(float(value), 0.0), 100.0)
            valid.add(news_id)
    return ParsedReactions(
        p_click=p_click,
        reactions=reactions,
        missing=tuple(i for i in ids if i not in valid),
    )


MessageBuilder = Callable[..., list[dict[str, str]]]
ARM_MESSAGES: dict[str, MessageBuilder] = {"A": arm_a_messages}

# A fixed fake user, rendered through every arm, so the hash covers everything that shapes
# the request: wording, layout, abstract length, schema, temperature and options.
_CANONICAL = CandidateSet(
    user_id="U0",
    impression_id="0",
    time=datetime(2019, 11, 15),
    items=("N1", "N2"),
    labels={"N1": 1, "N2": 0},
    tie_rank={"N1": 1, "N2": 0},
    feed_ctr=0.5,
    sample_ctr=0.5,
)
_CANONICAL_NEWS = {
    i: NewsItem(i, "news", "world", f"Headline {i}", "x" * (ABSTRACT_CHARS + 10))
    for i in ("N1", "N2")
}


def prompt_hashes(options: LLMOptions) -> dict[str, str]:
    """Short hash per arm of a fully rendered request (first attempt and retry)."""
    hashes = {}
    for arm, build in ARM_MESSAGES.items():
        messages = build(_CANONICAL, _CANONICAL_NEWS, base_rate_hint=options.base_rate_hint)
        rendered = [
            request_payload(messages, options),
            request_payload(retry_messages(messages, "<previous>"), options),
        ]
        blob = json.dumps(rendered, sort_keys=True).encode("utf-8")
        hashes[arm] = hashlib.sha256(blob).hexdigest()[:12]
    return hashes
