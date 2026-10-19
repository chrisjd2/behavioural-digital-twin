"""MIND loading, population sampling and candidate sets (ADR-0001, ADR-0005).

All randomness is seeded with strings, which Python's `random` hashes
deterministically, so results are stable across runs and machines.
"""

import csv
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MIND_TIME_FORMAT = "%m/%d/%Y %I:%M:%S %p"
MIN_HISTORY = 10
MIN_CLICKS = 1
MIN_NON_CLICKS = 3
MAX_CLICKED_CANDIDATES = 2


@dataclass(frozen=True)
class NewsItem:
    news_id: str
    category: str
    subcategory: str
    title: str
    abstract: str


@dataclass(frozen=True)
class Impression:
    impression_id: str
    user_id: str
    time: datetime
    history: tuple[str, ...]
    shown: tuple[tuple[str, int], ...]  # (news ID, clicked label) in feed order


@dataclass(frozen=True)
class Populations:
    dev: tuple[Impression, ...]
    test: tuple[Impression, ...]


@dataclass(frozen=True)
class CandidateSet:
    user_id: str
    impression_id: str
    items: tuple[str, ...]  # display order, shared by every arm
    labels: dict[str, int]
    tie_rank: dict[str, int]  # tie-break order, independent of display order
    feed_ctr: float  # click rate over the whole real impression
    sample_ctr: float  # click rate within the candidate set (inflated by design)


def load_news(path: Path) -> dict[str, NewsItem]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        return {
            row[0]: NewsItem(row[0], row[1], row[2], row[3], row[4] if len(row) > 4 else "")
            for row in rows
        }


def load_behaviors(path: Path) -> list[Impression]:
    impressions: list[Impression] = []
    with path.open(encoding="utf-8", newline="") as f:
        for impression_id, user_id, time, history, shown in csv.reader(
            f, delimiter="\t", quoting=csv.QUOTE_NONE
        ):
            impressions.append(
                Impression(
                    impression_id=impression_id,
                    user_id=user_id,
                    time=datetime.strptime(time, MIND_TIME_FORMAT),
                    history=tuple(history.split()),
                    shown=tuple(
                        (news_id, int(label))
                        for news_id, label in (token.rsplit("-", 1) for token in shown.split())
                    ),
                )
            )
    return impressions


def is_eligible(impression: Impression) -> bool:
    clicks = sum(label for _, label in impression.shown)
    non_clicks = len(impression.shown) - clicks
    return (
        len(impression.history) >= MIN_HISTORY
        and clicks >= MIN_CLICKS
        and non_clicks >= MIN_NON_CLICKS
    )


def sample_populations(
    impressions: list[Impression], *, n_dev: int, n_test: int, dev_seed: int, test_seed: int
) -> Populations:
    """One eligible impression per user; test drawn first so it never depends on the dev seed."""
    by_user: dict[str, list[Impression]] = defaultdict(list)
    for impression in impressions:
        if is_eligible(impression):
            by_user[impression.user_id].append(impression)

    users = sorted(by_user)
    if len(users) < n_dev + n_test:
        raise ValueError(f"Only {len(users)} eligible users; need {n_dev + n_test}")

    test_users = random.Random(f"test:{test_seed}").sample(users, n_test)
    remaining = sorted(set(users) - set(test_users))
    dev_users = random.Random(f"dev:{dev_seed}").sample(remaining, n_dev)

    def pick(user: str) -> Impression:
        options = sorted(by_user[user], key=lambda imp: imp.impression_id)
        return random.Random(f"impression:{user}").choice(options)

    return Populations(
        dev=tuple(pick(u) for u in dev_users), test=tuple(pick(u) for u in test_users)
    )


def build_candidate_set(impression: Impression, *, seed: int, max_candidates: int) -> CandidateSet:
    rng = random.Random(f"candidates:{seed}:{impression.user_id}:{impression.impression_id}")
    clicked = [news_id for news_id, label in impression.shown if label == 1]
    non_clicked = [news_id for news_id, label in impression.shown if label == 0]

    chosen_clicked = rng.sample(clicked, min(MAX_CLICKED_CANDIDATES, len(clicked)))
    n_fill = min(max_candidates - len(chosen_clicked), len(non_clicked))
    items = chosen_clicked + rng.sample(non_clicked, n_fill)
    rng.shuffle(items)

    tie_order = rng.sample(items, len(items))
    labels = {news_id: int(news_id in chosen_clicked) for news_id in items}
    return CandidateSet(
        user_id=impression.user_id,
        impression_id=impression.impression_id,
        items=tuple(items),
        labels=labels,
        tie_rank={news_id: rank for rank, news_id in enumerate(tie_order)},
        feed_ctr=len(clicked) / len(impression.shown),
        sample_ctr=len(chosen_clicked) / len(items),
    )
