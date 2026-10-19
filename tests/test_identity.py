"""The identity screen against the PR #37 reviews' adversarial phrasings, in both directions.

Every phrasing a reviewer reported (missed claims and flagged topics) is pinned here, so
the screen's precision and recall claims are checked against the real set, not a sample.
"""

import pytest

from backend.identity import identity_screen

SHOULD_FLAG = {
    "politics": [
        "The reader is a conservative who follows politics",
        "Conservative-leaning reader",
        "Politically liberal",
        "Leans left",
        "Votes Republican",
        "Supports Democrats",
        "Likely a progressive voter",
        "A Trump supporter",
    ],
    "religion": [
        "Is a devout Christian",
        "A devout Christian",
        "Religious reader",
        "Probably a practising Catholic",
        "Evangelical",
        "Churchgoer",
    ],
    "gender": ["Likely a mother of young children", "Presumably female", "Female reader"],
    "family": [
        "Has young kids",
        "Single mother",
        "Is married",
        "Married",
        "Is likely a grandmother",
        "Grandmother interested in recipes",
    ],
    "age": [
        "Probably retired, reads in the morning",
        "in their 30s, follows markets",
        "in his early 40s",
        "A man in his fifties",
        "Over 60",
        "65+",
        "Gen Z",
        "Approaching retirement",
        "Is a college student",
        "A student",
        "A baby boomer",
        "A 45-year-old",
        "45 year old",
    ],
    "health": [
        "Possibly pregnant given baby stories",
        "living with diabetes",
        "Diabetic reader",
        "Struggles with weight",
        "Suffers from anxiety",
        "Recovering alcoholic",
        "Is sober",
        "Battling obesity",
        "Is trying to lose weight",
    ],
    "location": [
        "Likely lives in Minnesota",
        "Based in California",
        "Probably from Minneapolis",
        "from Minneapolis",
    ],
    "occupation": [
        "Is a nurse",
        "Works as a teacher",
        "Likely a veteran",
        "A veteran",
        "Works in finance",
    ],
    "personality": ["Introverted", "Neurotic reader", "Anxious personality", "Outgoing person"],
    "income": [
        "Affluent household",
        "Is probably wealthy",
        "Working-class reader",
        "Wealthy homeowner",
        "High earner",
        "Upper-income",
        "Lives paycheck to paycheck",
    ],
    "ethnicity": ["Is likely Hispanic", "Asian American reader"],
    "sexuality": ["Probably gay", "LGBTQ reader", "Homosexual"],
}

TOPICS = [
    # Round 1
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
    # Round 2: reading verbs in the modifier slot
    "Likely clicks Republican primary coverage",
    "Probably interested in Christian music news",
    "Appears interested in Black Lives Matter coverage",
    "Possibly following the White Sox",
    "Likely follows the Rich Strike story",
    "Probably follows White House news",
    "Likely reads Black Friday deals",
    "Coverage is often about retired NFL players",
    "is mostly white-collar crime",
    "is focused on gay rights legislation",
    "Interest is largely single-game recaps",
    # Round 2: person nouns inside topics
    "a Black man shot by police",
    "a white woman arrested",
    "a retired man who won the lottery",
    "single parent household stories",
    # Round 2: numbers and phrases inside topics
    "TV personality interviews",
    "Radio personality news",
    "recipes under 30 minutes",
    "over 50 gift ideas",
    "50+ ideas for the holidays",
    "Over 60 percent of clicks are sports",
    "Gen Z trends and Gen X nostalgia",
    "Celebrities battling cancer",
    "a star who has cancer",
    "Tiny-house living in Alaska",
    "From recipes to travel guides",
]


@pytest.mark.parametrize(
    ("text", "kind"), [(text, kind) for kind, texts in SHOULD_FLAG.items() for text in texts]
)
def test_flags_claims_about_the_reader(text: str, kind: str) -> None:
    assert kind in {hit["kind"] for hit in identity_screen(text)}


@pytest.mark.parametrize("text", TOPICS)
def test_ignores_news_topics(text: str) -> None:
    assert identity_screen(text) == []
