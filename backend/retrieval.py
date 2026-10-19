"""Memories for the twins: which past clicks each twin is shown (ADR-0006).

Similarity comes from Gemini embeddings (cached in SQLite, embedded once per news item)
or, in mock mode and tests, a built-in TF-IDF. Selection is a pure function so the rules
are easy to test: top-3 similar past clicks per candidate plus the 3 most recent, deduped,
capped at 12, most recent kept on overflow.
"""

import hashlib
import math
import re
import sqlite3
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.data import NewsItem

SIMILAR_PER_CANDIDATE = 3
RECENT = 3
MAX_MEMORIES = 12
EMBED_BATCH = 100

Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]


@dataclass(frozen=True)
class Memory:
    news_id: str
    headline: str
    category: str
    reason: str  # "recent" or "similar to: <candidate headline>"


def news_text(item: NewsItem) -> str:
    return f"{item.category} {item.subcategory} {item.title} {item.abstract}".strip()


def select_memories(
    history: Sequence[str],
    candidates: Sequence[str],
    similarity: np.ndarray,  # shape (len(candidates), len(history))
    news: Mapping[str, NewsItem],
) -> list[Memory]:
    """The 3 most recent clicks, then round-robin: every candidate's best match, then every
    candidate's second-best, and so on, until 12. Round-robin keeps the cap from starving
    candidates late in the display order. A candidate the user already clicked before is
    never shown as a memory: the question is how they react to new content."""
    exclude = set(candidates)
    chosen: dict[str, str] = {}
    for news_id in reversed(history[-RECENT:]):
        if news_id not in exclude:
            chosen.setdefault(news_id, "recent")
    ranked = [
        [int(col) for col in np.argsort(-similarity[row], kind="stable")]
        for row in range(len(candidates))
    ]
    for rank in range(SIMILAR_PER_CANDIDATE):
        for row, candidate in enumerate(candidates):
            if len(chosen) >= MAX_MEMORIES:
                break
            matches = [history[c] for c in ranked[row] if history[c] not in exclude]
            if rank < len(matches):
                chosen.setdefault(matches[rank], f"similar to: {news[candidate].title}")
    return [
        Memory(news_id, news[news_id].title, _category(news[news_id]), reason)
        for news_id, reason in list(chosen.items())[:MAX_MEMORIES]
    ]


def _category(item: NewsItem) -> str:
    return f"{item.category}/{item.subcategory}"  # the same form the candidates are shown in


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


class TfidfIndex:
    """Plain TF-IDF over category, subcategory, title and abstract. No network, no cost."""

    def __init__(self, news: Mapping[str, NewsItem]) -> None:
        self._tokens = {
            i: Counter(re.findall(r"[a-z0-9]+", news_text(n).lower())) for i, n in news.items()
        }
        df = Counter(token for counts in self._tokens.values() for token in counts)
        n_docs = len(self._tokens)
        self._idf = {t: math.log((1 + n_docs) / (1 + d)) + 1 for t, d in df.items()}

    def similarity(self, rows: Sequence[str], cols: Sequence[str]) -> np.ndarray:
        # Only the words these items use: a few hundred columns, not the whole vocabulary.
        ids = [*rows, *cols]
        vocab = {t: k for k, t in enumerate(sorted({t for i in ids for t in self._tokens[i]}))}
        matrix = np.zeros((len(ids), len(vocab)), dtype=np.float32)
        for row, news_id in enumerate(ids):
            for token, count in self._tokens[news_id].items():
                matrix[row, vocab[token]] = count * self._idf[token]
        matrix = _normalise(matrix)
        return matrix[: len(rows)] @ matrix[len(rows) :].T


class EmbeddingStore:
    """Unit-length vectors per (base URL, model, dimensions, text hash), stored in SQLite."""

    def __init__(
        self, path: Path, *, base_url: str, model: str, dimensions: int, embed: Embedder
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS embedding_vectors "
            "(base_url TEXT, model TEXT, dims INTEGER, text_sha TEXT, vector BLOB, "
            "PRIMARY KEY (base_url, model, dims, text_sha))"
        )
        self.base_url, self.model, self.dimensions = base_url, model, dimensions
        self._embed = embed
        self.calls = 0
        self._vectors: dict[str, np.ndarray] = {}

    async def ensure(self, news: Mapping[str, NewsItem], ids: Sequence[str]) -> None:
        """Embed (once, ever) any of `ids` not already cached."""
        missing: dict[str, str] = {}
        for news_id in dict.fromkeys(ids):
            if news_id in self._vectors:
                continue
            text = news_text(news[news_id])
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            row = self._db.execute(
                "SELECT vector FROM embedding_vectors "
                "WHERE base_url=? AND model=? AND dims=? AND text_sha=?",
                (self.base_url, self.model, self.dimensions, sha),
            ).fetchone()
            if row:
                self._vectors[news_id] = np.frombuffer(row[0], dtype=np.float32)
            else:
                missing[news_id] = text
        pending = list(missing.items())
        for start in range(0, len(pending), EMBED_BATCH):
            batch = pending[start : start + EMBED_BATCH]
            raw = np.asarray(await self._embed([text for _, text in batch]), dtype=np.float32)
            self.calls += 1
            for (news_id, text), vector in zip(batch, _normalise(raw), strict=True):
                sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
                self._db.execute(
                    "INSERT OR REPLACE INTO embedding_vectors VALUES (?, ?, ?, ?, ?)",
                    (self.base_url, self.model, self.dimensions, sha, vector.tobytes()),
                )
                self._vectors[news_id] = vector
            self._db.commit()  # per batch, so a failure later keeps what was already paid for

    def similarity(self, rows: Sequence[str], cols: Sequence[str]) -> np.ndarray:
        return (
            np.stack([self._vectors[i] for i in rows])
            @ np.stack([self._vectors[i] for i in cols]).T
        )


class Retriever:
    """Picks a user's memories with whichever vector source the run uses."""

    def __init__(self, news: Mapping[str, NewsItem], store: EmbeddingStore | None) -> None:
        self.news = news
        self.store = store
        self.method = f"embeddings:{store.model}:{store.dimensions}" if store else "tfidf"
        self._tfidf = None if store else TfidfIndex(news)

    async def prepare(self, ids: Sequence[str]) -> None:
        if self.store:
            await self.store.ensure(self.news, ids)

    def memories(self, history: Sequence[str], candidates: Sequence[str]) -> list[Memory]:
        if not history:
            return []
        source = self.store or self._tfidf
        assert source is not None
        similarity = source.similarity(list(candidates), list(history))
        return select_memories(history, candidates, similarity, self.news)
