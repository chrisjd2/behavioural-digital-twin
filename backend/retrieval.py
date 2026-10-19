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
    """Most recent first, then each candidate's top matches in display order; cap 12."""
    chosen: dict[str, str] = {}
    for news_id in reversed(history[-RECENT:]):
        chosen.setdefault(news_id, "recent")
    for row, candidate in enumerate(candidates):
        order = np.argsort(-similarity[row], kind="stable")[:SIMILAR_PER_CANDIDATE]
        for col in order:
            chosen.setdefault(history[int(col)], f"similar to: {news[candidate].title}")
    return [
        Memory(news_id, news[news_id].title, news[news_id].category, reason)
        for news_id, reason in list(chosen.items())[:MAX_MEMORIES]
    ]


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
        self._vocab = {t: k for k, t in enumerate(sorted(self._idf))}

    def vectors(self, ids: Sequence[str]) -> np.ndarray:
        matrix = np.zeros((len(ids), len(self._vocab)), dtype=np.float32)
        for row, news_id in enumerate(ids):
            for token, count in self._tokens[news_id].items():
                matrix[row, self._vocab[token]] = count * self._idf[token]
        return _normalise(matrix)


class EmbeddingStore:
    """Unit-length embedding vectors per (model, dimensions, text hash), stored in SQLite."""

    def __init__(self, path: Path, *, model: str, dimensions: int, embed: Embedder) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS embeddings "
            "(model TEXT, dims INTEGER, text_sha TEXT, vector BLOB, "
            "PRIMARY KEY (model, dims, text_sha))"
        )
        self.model, self.dimensions, self._embed = model, dimensions, embed
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
                "SELECT vector FROM embeddings WHERE model=? AND dims=? AND text_sha=?",
                (self.model, self.dimensions, sha),
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
                    "INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?, ?)",
                    (self.model, self.dimensions, sha, vector.tobytes()),
                )
                self._vectors[news_id] = vector
        self._db.commit()

    def vectors(self, ids: Sequence[str]) -> np.ndarray:
        return np.stack([self._vectors[i] for i in ids])


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
        history = [h for h in history if h in self.news]
        if not history:
            return []
        source = self.store or self._tfidf
        assert source is not None
        similarity = source.vectors(list(candidates)) @ source.vectors(history).T
        return select_memories(history, candidates, similarity, self.news)
