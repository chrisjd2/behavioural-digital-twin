"""Invented personas for arm B (ADR-0003).

Inspired by Maiorano (2026), not a reproduction: one made-up person per user rather than
an averaged panel. Seeded from the user ID only, so it never depends on the user's data.
"""

import random

FIRST_NAMES = (
    "Alex", "Maria", "James", "Priya", "Daniel", "Grace", "Carlos", "Mei", "Robert", "Aisha",
    "Tom", "Sofia", "Kevin", "Hannah", "Luis", "Emily", "Marcus", "Olivia", "Ethan", "Nadia",
)  # fmt: skip
LAST_NAMES = (
    "Johnson", "Garcia", "Nguyen", "Patel", "Miller", "Kim", "Brown", "Lopez", "Wilson",
    "Chen", "Davis", "Martinez", "Taylor", "Okafor", "Anderson", "Rossi",
)  # fmt: skip
MIN_AGE, MAX_AGE = 19, 78
JOBS = (
    "nurse", "high-school teacher", "software developer", "truck driver", "accountant",
    "retail store manager", "electrician", "graduate student", "retired postal worker",
    "real-estate agent", "chef", "marketing coordinator", "police officer", "farmer",
    "dental hygienist", "small-business owner", "warehouse supervisor", "pharmacist",
)  # fmt: skip
LOCATIONS = (
    "Seattle, Washington", "Austin, Texas", "Columbus, Ohio", "Atlanta, Georgia",
    "Phoenix, Arizona", "Boston, Massachusetts", "Denver, Colorado", "Tampa, Florida",
    "Omaha, Nebraska", "Sacramento, California", "Pittsburgh, Pennsylvania",
    "Nashville, Tennessee", "Minneapolis, Minnesota", "a small town in rural Iowa",
)  # fmt: skip
BIG_FIVE = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
LEVELS = ("low", "medium", "high")
SCHWARTZ_VALUES = (
    "self-direction", "stimulation", "hedonism", "achievement", "power",
    "security", "conformity", "tradition", "benevolence", "universalism",
)  # fmt: skip
NEWS_HABITS = (
    "You skim headlines on your phone during your morning commute.",
    "You read the news over coffee most mornings, a few stories in depth.",
    "You check the news in short bursts during breaks at work.",
    "You scroll through your feed in the evening to wind down.",
    "You mostly follow news that friends and family mention to you.",
    "You glance at headlines a couple of times a week and rarely click through.",
    "You catch up on the news at weekends, reading longer pieces.",
)


def invent_persona(user_id: str) -> dict[str, object]:
    rng = random.Random(f"persona:{user_id}")
    return {
        "invented": True,  # made up; not from this user's data
        "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
        "age": rng.randint(MIN_AGE, MAX_AGE),
        "job": rng.choice(JOBS),
        "location": rng.choice(LOCATIONS),
        "big_five": {trait: rng.choice(LEVELS) for trait in BIG_FIVE},
        "values": rng.sample(SCHWARTZ_VALUES, 2),
        "news_habit": rng.choice(NEWS_HABITS),
    }
