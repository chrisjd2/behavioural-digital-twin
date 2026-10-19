"""Arm D's distilled profile and the identity screen (ADR-0007).

One LLM call per user (cached like every call) turns the last <= 50 clicks into a short,
structured, evidence-cited profile. Items that cite clicks the user never made are dropped
and counted. The identity screen then looks for inferences about who the person *is*
(age, gender, beliefs, health, sexuality, ethnicity, income): hits are flagged and counted,
never blocking, so the Report can show how often the guardrail was needed.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.data import NewsItem

PROFILE_CLICKS = 50
PROFILE_WORD_LIMIT = 120
PROFILE_FIELDS = ("interests", "rarely_clicks", "style_preferences", "recent_shifts")

_ITEM = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "evidence"],
    "additionalProperties": False,
}
PROFILE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {field: {"type": "array", "items": _ITEM} for field in PROFILE_FIELDS},
    "required": list(PROFILE_FIELDS),
    "additionalProperties": False,
}

PROFILE_SYSTEM = (
    "You summarise one person's news-click history into a short reading profile, using only "
    "evidence in the history. Write at most 120 words in total across all fields.\n"
    "- interests: topics and kinds of story they click.\n"
    "- rarely_clicks: topics noticeably absent or rare; cite the clicks that show where their "
    "attention goes instead.\n"
    "- style_preferences: formats or tones they favour (e.g. explainers, lists, breaking news).\n"
    "- recent_shifts: how the most recent clicks differ from earlier ones, if at all.\n"
    "Every item must cite one or more click ids from the history as evidence.\n"
    "Describe reading habits only. Never state or guess demographics (age, gender, location, "
    "income, ethnicity), personality, political or religious affiliation, health status or "
    "sexuality. 'Follows election coverage' is fine; 'is a conservative' is not."
)

# The screen looks for claims about who the person IS ("is a conservative", "likely a
# mother", "in their 30s"), not topic words: "Black Friday", "White House" and "Republican
# primary" are news, not inferences. It measures, it never blocks (ADR-0007).
_CLAIM = (
    r"\b(?:is|are|was|seems|appears|likely|probably|possibly|perhaps|as|being)\s+(?:an?\s+|the\s+)?"
)
IDENTITY_TERMS = {
    "age": r"(?:teenager|retiree|retired|elderly|senior citizen|millennial|boomer|student)",
    "gender": r"(?:man|woman|male|female|mother|father|mom|dad|parent|wife|husband)",
    "politics": r"(?:liberal|conservative|democrat|republican|progressive|left[- ]wing|right[- ]wing)",
    "religion": r"(?:christian|muslim|jewish|catholic|protestant|hindu|buddhist|atheist|religious)",
    "health": r"(?:diabetic|pregnant|disabled|depressed|ill|sick|overweight|obese|in recovery)",
    "sexuality": r"(?:gay|lesbian|bisexual|straight|queer|transgender|lgbt\w*)",
    "ethnicity": r"(?:black|white|hispanic|latino|latina|asian|african[- ]american)",
    "income": r"(?:wealthy|rich|affluent|low[- ]income|poor|working[- ]class|middle[- ]class)",
}
_DIRECT = {  # phrasings that are inferences on their own, with no "is a" in front
    "age": r"\b(?:\d{1,2}[- ]years?[- ]old|aged \d{1,2}|in (?:their|his|her) (?:teens|\d0s))\b",
    "health": r"\b(?:has|have|living with) (?:diabetes|cancer|depression|anxiety|a disability)\b",
}
_IDENTITY = {
    kind: re.compile(
        _CLAIM + term + r"\b" + (f"|{_DIRECT[kind]}" if kind in _DIRECT else ""), re.IGNORECASE
    )
    for kind, term in IDENTITY_TERMS.items()
}


@dataclass(frozen=True)
class Profile:
    fields: dict[str, list[dict[str, object]]]  # field -> [{"text", "evidence": [ids]}]
    dropped_items: int  # items citing clicks the user never made, or none at all
    word_count: int
    identity_hits: list[dict[str, str]]  # [{"kind", "term", "text"}]
    ok: bool  # parsed, within the word limit, and at least one valid item


def profile_messages(history: Sequence[str], news: Mapping[str, NewsItem]) -> list[dict[str, str]]:
    clicks = [
        {
            "id": i,
            "category": f"{news[i].category}/{news[i].subcategory}",
            "headline": news[i].title,
        }
        for i in history[-PROFILE_CLICKS:]
    ]
    listing = json.dumps(clicks, indent=1, ensure_ascii=False)
    return [
        {"role": "system", "content": PROFILE_SYSTEM},
        {"role": "user", "content": f"Click history, oldest first:\n{listing}"},
    ]


def identity_screen(text: str) -> list[dict[str, str]]:
    return [
        {"kind": kind, "term": match.group(0), "text": text}
        for kind, pattern in _IDENTITY.items()
        for match in pattern.finditer(text)
    ]


def parse_profile(content: str, history: Sequence[str]) -> Profile:
    allowed = set(history[-PROFILE_CLICKS:])
    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        raw = None
    fields: dict[str, list[dict[str, object]]] = {f: [] for f in PROFILE_FIELDS}
    dropped = 0
    for field in PROFILE_FIELDS:
        items = raw.get(field, []) if isinstance(raw, dict) else []
        for item in items if isinstance(items, list) else []:
            text = item.get("text") if isinstance(item, dict) else None
            evidence = item.get("evidence") if isinstance(item, dict) else None
            cited = [e for e in evidence if e in allowed] if isinstance(evidence, list) else []
            if not isinstance(text, str) or not text.strip() or not cited:
                dropped += 1
                continue
            fields[field].append({"text": text.strip(), "evidence": cited})
    texts = [str(item["text"]) for items in fields.values() for item in items]
    word_count = sum(len(t.split()) for t in texts)
    return Profile(
        fields=fields,
        dropped_items=dropped,
        word_count=word_count,
        identity_hits=[hit for t in texts for hit in identity_screen(t)],
        ok=raw is not None and bool(texts) and word_count <= PROFILE_WORD_LIMIT,
    )


def profile_block(fields: Mapping[str, Sequence[Mapping[str, object]]]) -> str:
    """The profile as the agent sees it: text only; evidence ids stay in the run file."""
    lines = []
    for field in PROFILE_FIELDS:
        items = fields.get(field, [])
        if items:
            label = field.replace("_", " ").capitalize()
            lines.append(f"{label}: " + "; ".join(str(item["text"]) for item in items))
    return "\n".join(lines)
