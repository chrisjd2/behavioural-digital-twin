"""Synthetic MIND-format data for tests and offline development. Fake: never present as results.

Users prefer two categories and click those far more often, and some items are
more popular than others, so arms and baselines have real signal to find.
"""

import random
from datetime import datetime, timedelta
from pathlib import Path

from backend.data import MIND_TIME_FORMAT

CATEGORIES = {
    "news": ["politics", "world", "science"],
    "sports": ["football_nfl", "basketball_nba", "soccer"],
    "finance": ["markets", "personalfinance", "companies"],
    "lifestyle": ["home", "relationships", "style"],
    "health": ["fitness", "medical", "nutrition"],
    "entertainment": ["movies", "tv", "music"],
    "travel": ["destinations", "tips", "adventure"],
    "foodanddrink": ["recipes", "restaurants", "drinks"],
}
DEV_DAY = datetime(2019, 11, 15)
TRAIN_DAYS = 6  # train covers the days before the dev day, as in MIND
MARKER_FILE = "SYNTHETIC"


def is_synthetic(directory: Path) -> bool:
    """True when `directory` holds generated fake data rather than real MIND."""
    return (directory / MARKER_FILE).exists()


def write_synthetic_sample(directory: Path, *, n_users: int, n_news: int, seed: int) -> None:
    """Write `dev/` and `train/` splits in MIND layout; train impressions all precede dev."""
    rng = random.Random(f"sample:{seed}")
    for split in ("dev", "train"):
        (directory / split).mkdir(parents=True, exist_ok=True)
    (directory / MARKER_FILE).write_text(
        "Synthetic MIND-format data for tests and development. Not real; never report results.\n",
        encoding="utf-8",
    )

    news: list[tuple[str, str, float]] = []  # (id, category, popularity)
    rows: list[str] = []
    for n in range(n_news):
        news_id = f"N{n + 1}"
        category = rng.choice(list(CATEGORIES))
        subcategory = rng.choice(CATEGORIES[category])
        news.append((news_id, category, rng.betavariate(1, 4)))
        title = f"[SYNTHETIC] {subcategory.replace('_', ' ').title()} story {n + 1}"
        abstract = f"Synthetic {category} abstract for testing only."
        rows.append(f"{news_id}\t{category}\t{subcategory}\t{title}\t{abstract}\t\t[]\t[]\n")
    for split in ("dev", "train"):
        (directory / split / "news.tsv").write_text("".join(rows), encoding="utf-8", newline="\n")

    impression_id = 0
    lines: dict[str, list[str]] = {"dev": [], "train": []}
    for u in range(n_users):
        user_id = f"U{u + 1}"
        liked = set(rng.sample(list(CATEGORIES), 2))
        preferred = [item for item in news if item[1] in liked]
        others = [item for item in news if item[1] not in liked]
        history = " ".join(
            dict.fromkeys(
                rng.choice(preferred if rng.random() < 0.8 else others)[0]
                for _ in range(rng.randint(5, 40))
            )
        )
        splits = ["train"] * rng.randint(0, 3) + ["dev"] * rng.randint(1, 3)
        for split in splits:
            impression_id += 1
            shown = rng.sample(news, rng.randint(10, 30))
            tokens = " ".join(
                f"{news_id}-{int(rng.random() < (0.3 if cat in liked else 0.03) * (0.5 + pop))}"
                for news_id, cat, pop in shown
            )
            days_before = 0 if split == "dev" else rng.randint(1, TRAIN_DAYS)
            time = DEV_DAY - timedelta(days=days_before) + timedelta(seconds=rng.randint(0, 86_399))
            lines[split].append(
                f"{impression_id}\t{user_id}\t{time.strftime(MIND_TIME_FORMAT)}\t{history}\t{tokens}\n"
            )
    for split, split_lines in lines.items():
        (directory / split / "behaviors.tsv").write_text(
            "".join(split_lines), encoding="utf-8", newline="\n"
        )
