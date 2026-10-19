"""Prompt builders and output parsing for the LLM arms (ADR-0003, ADR-0005).

Every arm shares the output format, the feed framing and the display order;
only the system prompt (what the agent knows) differs.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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

FEED_INSTRUCTIONS = (
    "Each of these headlines appeared in your Microsoft News feed while you were browsing, "
    "among many others. For each one, give your honest one-sentence first-person gut reaction, "
    "then the probability (0-100) that you clicked it.\n"
    'Reply with JSON only: {"reactions": [{"id": ..., "reaction": ..., "p_click": ...}]}, '
    "one entry per headline id."
)

BASE_RATE_HINT = "For context: readers click only about 4% of the headlines in their feed."

RETRY_INSTRUCTION = (
    "Your previous reply was not valid. Return valid JSON only, with exactly one entry for "
    "every headline id listed."
)

TEMPLATES = {"A": (ARM_A_SYSTEM, FEED_INSTRUCTIONS, BASE_RATE_HINT, RETRY_INSTRUCTION)}


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


def request_payload(messages: list[dict[str, str]]) -> dict[str, object]:
    return {
        "messages": messages,
        "temperature": 0,
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
        if isinstance(value, int | float) and not isinstance(value, bool):
            p_click[news_id] = min(max(float(value), 0.0), 100.0)
            valid.add(news_id)
    return ParsedReactions(
        p_click=p_click,
        reactions=reactions,
        missing=tuple(i for i in ids if i not in valid),
    )


def prompt_hashes() -> dict[str, str]:
    """Short hash of each arm's prompt templates, recorded in every run file."""
    return {
        arm: hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]
        for arm, parts in TEMPLATES.items()
    }
