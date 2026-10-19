"""Invented personas for arm B (ADR-0003).

Inspired by Maiorano (2026), not a reproduction: one made-up person per user rather than
an averaged panel. Seeded from the user ID only, so it never depends on the user's data.
A life stage is drawn first and fixes age, job and news habit, so each person is plausible
and arm B is not a straw man.
"""

import random
from dataclasses import dataclass

FIRST_NAMES = (
    "Alex", "Maria", "James", "Priya", "Daniel", "Grace", "Carlos", "Mei", "Robert", "Aisha",
    "Tom", "Sofia", "Kevin", "Hannah", "Luis", "Emily", "Marcus", "Olivia", "Ethan", "Nadia",
)  # fmt: skip
LAST_NAMES = (
    "Johnson", "Garcia", "Nguyen", "Patel", "Miller", "Kim", "Brown", "Lopez", "Wilson",
    "Chen", "Davis", "Martinez", "Taylor", "Okafor", "Anderson", "Rossi",
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
LATE_CAREER_JOBS = (
    "school principal", "plant manager", "nurse", "accountant", "small-business owner",
    "postal worker", "civil engineer", "insurance agent", "farmer", "pharmacist",
)  # fmt: skip


@dataclass(frozen=True)
class LifeStage:
    min_age: int
    max_age: int
    jobs: tuple[str, ...]
    news_habits: tuple[str, ...]


LIFE_STAGES = {
    "student": LifeStage(
        18,
        24,
        (
            "college student",
            "community-college student",
            "graduate student",
            "trade-school student",
        ),
        (
            "You scroll news on your phone between classes, mostly what friends share.",
            "You catch headlines on social media late at night and rarely read past them.",
        ),
    ),
    "early career": LifeStage(
        25,
        34,
        (
            "software developer",
            "nurse",
            "marketing coordinator",
            "electrician",
            "high-school teacher",
            "line cook",
            "sales associate",
            "paralegal",
        ),
        (
            "You skim headlines on your phone during your morning commute.",
            "You scroll through your feed in the evening to wind down.",
        ),
    ),
    "mid career": LifeStage(
        35,
        49,
        (
            "accountant",
            "police officer",
            "real-estate agent",
            "warehouse supervisor",
            "dental hygienist",
            "project manager",
            "truck driver",
            "physical therapist",
        ),
        (
            "You check the news in short bursts during breaks at work.",
            "You glance at headlines once the kids are in bed and click a few.",
        ),
    ),
    "late career": LifeStage(
        50,
        65,
        LATE_CAREER_JOBS,
        (
            "You read the news over coffee most mornings, a few stories in depth.",
            "You check the news at lunch and again in the evening.",
        ),
    ),
    "retired": LifeStage(
        66,
        80,
        tuple(f"retired {job}" for job in LATE_CAREER_JOBS),
        (
            "You read the news at length every morning and follow stories for days.",
            "You catch up on the news through the day, between errands and hobbies.",
        ),
    ),
}


def invent_persona(user_id: str) -> dict[str, object]:
    rng = random.Random(f"persona:{user_id}")
    life_stage = rng.choice(list(LIFE_STAGES))
    stage = LIFE_STAGES[life_stage]
    return {
        "invented": True,  # made up; not from this user's data
        "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
        "life_stage": life_stage,
        "age": rng.randint(stage.min_age, stage.max_age),
        "job": rng.choice(stage.jobs),
        "location": rng.choice(LOCATIONS),
        # Personality and values vary independently of life stage, as they do in people.
        "big_five": {trait: rng.choice(LEVELS) for trait in BIG_FIVE},
        "values": rng.sample(SCHWARTZ_VALUES, 2),
        "news_habit": rng.choice(stage.news_habits),
    }
