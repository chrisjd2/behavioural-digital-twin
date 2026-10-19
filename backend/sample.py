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
DAY = datetime(2019, 11, 15)
MARKER_FILE = "SYNTHETIC"


def is_synthetic(directory: Path) -> bool:
    """True when `directory` holds generated fake data rather than real MIND."""
    return (directory / MARKER_FILE).exists()


def write_synthetic_sample(directory: Path, *, n_users: int, n_news: int, seed: int) -> None:
    rng = random.Random(f"sample:{seed}")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / MARKER_FILE).write_text(
        "Synthetic MIND-format data for tests and development. Not real; never report results.\n",
        encoding="utf-8",
    )

    news: list[tuple[str, str, float]] = []  # (id, category, popularity)
    with (directory / "news.tsv").open("w", encoding="utf-8", newline="\n") as f:
        for n in range(n_news):
            news_id = f"N{n + 1}"
            category = rng.choice(list(CATEGORIES))
            subcategory = rng.choice(CATEGORIES[category])
            popularity = rng.betavariate(1, 4)
            news.append((news_id, category, popularity))
            title = f"[SYNTHETIC] {subcategory.replace('_', ' ').title()} story {n + 1}"
            abstract = f"Synthetic {category} abstract for testing only."
            f.write(f"{news_id}\t{category}\t{subcategory}\t{title}\t{abstract}\t\t[]\t[]\n")

    impression_id = 0
    with (directory / "behaviors.tsv").open("w", encoding="utf-8", newline="\n") as f:
        for u in range(n_users):
            user_id = f"U{u + 1}"
            liked = set(rng.sample(list(CATEGORIES), 2))
            preferred = [item for item in news if item[1] in liked]
            others = [item for item in news if item[1] not in liked]
            history = [
                rng.choice(preferred if rng.random() < 0.8 else others)[0]
                for _ in range(rng.randint(5, 40))
            ]
            for _ in range(rng.randint(1, 3)):
                impression_id += 1
                shown = rng.sample(news, rng.randint(10, 30))
                tokens = [
                    f"{news_id}-{int(rng.random() < (0.3 if cat in liked else 0.03) * (0.5 + pop))}"
                    for news_id, cat, pop in shown
                ]
                time = DAY + timedelta(seconds=rng.randint(0, 86_399))
                f.write(
                    f"{impression_id}\t{user_id}\t{time.strftime(MIND_TIME_FORMAT)}"
                    f"\t{' '.join(dict.fromkeys(history))}\t{' '.join(tokens)}\n"
                )
