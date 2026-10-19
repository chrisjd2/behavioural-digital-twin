"""The identity screen (ADR-0007): does a profile item claim who the reader IS?

Profiles describe reading habits as short items ("Celebrity gossip and true crime",
"Few or no clicks on politics"). An identity claim is about the *reader*, so it shows up in
three places, and the screen only looks there:

- after a claim word: "is a devout Christian", "likely a mother", "presumably female";
- at the start of an item, as a fragment that ends its clause: "A devout Christian",
  "Married", "Wealthy homeowner", "Diabetic reader", "Gen Z", "A 45-year-old";
- as a verb about the reader at the start of an item: "Votes Republican", "Lives in Ohio",
  "Has young kids", "Struggles with weight".

Topics come after reading verbs and prepositions ("Likely clicks Republican primary
coverage", "is mostly white-collar crime") or run on into a topic noun ("Gen Z trends",
"over 50 gift ideas", "a 40-year-old record"), and are not flagged. The screen measures;
it never blocks, and a person reviews every flag.
"""

import re

# Claim words, then up to two modifiers that are not reading verbs or prepositions.
_NOT_A_MODIFIER = (
    r"(?:clicks?|clicking|reads?|reading|follows?|following|interested|interest|drawn|focused|"
    r"about|in|on|of|to|into|with|for|the|mostly|mainly|largely|often|usually|coverage|news|"
    r"stories|story|articles?)"
)
_CLAIM = (
    r"\b(?:is|are|was|seems|appears|likely|probably|possibly|perhaps|presumably|apparently)"
    rf"\s+(?:to\s+be\s+)?(?:an?\s+)?(?:(?!{_NOT_A_MODIFIER}\b)[\w-]+\s+){{0,2}}?"
)
_START = r"^\s*(?:(?:likely|probably|possibly|presumably|apparently)\s+)?(?:an?\s+)?"
_END = (
    r"(?=\s*(?:$|[,.;:!?]|\b(?:and|with|interested|reader|person)\b"
    r"|household\s*(?:$|[,.;:!?])))"
)
_WORD_END = r"(?![\w-])"  # "single" is not "single-game"; "white" is not "white-collar"

TERMS = {
    "age": r"(?:teenager|teen|retiree|retired|elderly|senior citizen|millennial|baby\s+boomer|boomer|student|young\s+adult)",
    "gender": r"(?:male|female|mother|father|mom|dad|wife|husband|woman|man)",
    "family": r"(?:married|divorced|widow(?:ed|er)?|grandmother|grandfather|grandparent|single\s+(?:mother|father|parent|mom|dad))",
    "occupation": r"(?:nurse|teacher|doctor|engineer|lawyer|farmer|veteran|homemaker|executive)",
    "politics": r"(?:liberal|conservative|democrat|republican|progressive|left[- ]wing|right[- ]wing|\w+\s+supporter)",
    "religion": r"(?:devout\s+\w+|christian|muslim|jewish|catholic|protestant|evangelical|churchgoer|hindu|buddhist|atheist|religious)",
    "health": r"(?:diabetic|pregnant|disabled|depressed|anxious|sick|overweight|obese|alcoholic|sober|addict)",
    "sexuality": r"(?:gay|lesbian|bisexual|homosexual|queer|transgender|lgbt\w*)",
    "ethnicity": r"(?:african[- ]american|asian[- ]american|black|white|hispanic|latino|latina|asian)",
    "income": r"(?:wealthy|rich|affluent|high[- ]earner|upper[- ]income|low[- ]income|poor|working[- ]class|middle[- ]class|homeowner)",
    "personality": r"(?:introvert(?:ed)?|extrovert(?:ed)?|neurotic|impulsive|shy|outgoing)",
}

# Forms about the reader at the start of an item (after an optional hedge word).
_ITEM_START = {
    "politics": r"(?:leans?\s+(?:left|right|liberal|conservative)|votes?\s+\w+|supports?\s+(?:democrats|republicans|trump|biden)|politically\s+\w+|\w+-leaning)",
    "health": r"(?:(?:has|have|living\s+with|struggles?\s+with|suffers?\s+from|battling|recovering\s+from)\s+(?:diabetes|cancer|depression|anxiety|obesity|weight|addiction|an?\s+(?:illness|disability))|trying\s+to\s+lose\s+weight)",
    "family": r"(?:has|have)\s+(?:(?:young|grown|small|teenage)\s+)?(?:kids|children|grandchildren)",
    "location": r"(?:lives?|living|based|located|resides?)\s+in\s+\w+|from\s+[a-z]+",
    "occupation": r"(?:works?|employed)\s+(?:as|in)\s+(?:an?\s+)?\w+",
    "income": r"lives?\s+paycheck\s+to\s+paycheck",
    "age": r"(?:nearing|approaching)\s+retirement|\d{1,2}[- ]years?[- ]old|(?:over|under|aged?)\s+\d{2}|\d{2}\+|gen\s?[xyz]|(?:early|mid|late)[- ]\d0s",
}

# Unambiguous anywhere: an age bracket attached to a person.
_ANYWHERE = {
    "age": r"\bin\s+(?:their|his|her)\s+(?:early\s+|mid[- ]?|late\s+)?(?:teens|\d0s|twenties|thirties|forties|fifties|sixties|seventies)\b",
    "personality": r"\b(?:introvert\w*|extrovert\w*|anxious|outgoing|shy|impulsive|neurotic)\s+personality\b",
}


def _compile(kind: str) -> re.Pattern[str]:
    parts = []
    if kind in TERMS:
        term = TERMS[kind]
        parts += [_CLAIM + term + _WORD_END, _START + r"(?:[\w-]+\s+)?" + term + _WORD_END + _END]
    if kind in _ITEM_START:
        parts.append(_START + r"(?:is\s+)?(?:" + _ITEM_START[kind] + r")" + _WORD_END + _END)
    if kind in _ANYWHERE:
        parts.append(_ANYWHERE[kind])
    return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


_PATTERNS = {kind: _compile(kind) for kind in {*TERMS, *_ITEM_START, *_ANYWHERE}}


def identity_screen(text: str) -> list[dict[str, str]]:
    """Every identity claim found in one profile item, as {kind, term, text}."""
    return [
        {"kind": kind, "term": match.group(0).strip(), "text": text}
        for kind, pattern in sorted(_PATTERNS.items())
        for match in pattern.finditer(text)
    ]
