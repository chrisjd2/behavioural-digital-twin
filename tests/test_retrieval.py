from pathlib import Path

import numpy as np
import pytest

from backend.arms import ARM_SPECS, ArmResources, LLMOptions
from backend.data import DataSource, NewsItem, build_candidate_set, load_news
from backend.experiment import ExperimentConfig
from backend.llm import Cache, LLMClient, mock_backend
from backend.retrieval import (
    MAX_MEMORIES,
    EmbeddingStore,
    Retriever,
    TfidfIndex,
    select_memories,
)
from backend.runner import run_experiment
from tests.factories import make_impression

NEWS = {f"H{i}": NewsItem(f"H{i}", "sports", "nfl", f"History {i}", "") for i in range(20)} | {
    f"C{i}": NewsItem(f"C{i}", "sports", "nfl", f"Candidate {i}", "") for i in range(8)
}


def test_recent_first_then_top_three_per_candidate_with_reasons() -> None:
    history = ["H0", "H1", "H2", "H3", "H4"]
    similarity = np.array([[0.9, 0.8, 0.7, 0.1, 0.0]])  # one candidate: H0 > H1 > H2

    memories = select_memories(history, ["C0"], similarity, NEWS)

    assert [m.news_id for m in memories] == ["H4", "H3", "H2", "H0", "H1"]
    assert [m.reason for m in memories[:3]] == ["recent"] * 3  # H2 is recent and similar
    assert memories[3].reason == "similar to: Candidate 0"


def test_duplicates_are_listed_once() -> None:
    history = [f"H{i}" for i in range(10)]
    same_order = np.tile(np.linspace(1, 0, 10), (2, 1))  # both candidates like H0..H2

    memories = select_memories(history, ["C0", "C1"], same_order, NEWS)

    ids = [m.news_id for m in memories]
    assert len(ids) == len(set(ids)) == 6
    assert {m.reason for m in memories if m.news_id == "H0"} == {"similar to: Candidate 0"}


def test_cap_keeps_the_most_recent_on_overflow() -> None:
    history = [f"H{i}" for i in range(20)]
    rng = np.random.default_rng(0)
    similarity = rng.random((8, 20))
    similarity[:, 17:] = -1  # recent items are never "similar"

    memories = select_memories(history, [f"C{i}" for i in range(8)], similarity, NEWS)

    assert len(memories) == MAX_MEMORIES
    assert [m.news_id for m in memories[:3]] == ["H19", "H18", "H17"]


def test_tfidf_prefers_shared_words() -> None:
    news = {
        "a": NewsItem("a", "sports", "nfl", "Patriots win playoff game", ""),
        "b": NewsItem("b", "sports", "nfl", "Patriots playoff hopes", ""),
        "c": NewsItem("c", "food", "recipes", "Easy pumpkin pie", ""),
    }
    vectors = TfidfIndex(news).vectors(["a", "b", "c"])

    assert vectors[0] @ vectors[1] > vectors[0] @ vectors[2]


def fake_embedder(calls: list[int]):
    async def embed(texts: list[str]) -> list[list[float]]:
        calls.append(len(texts))
        return [[float(len(t)), 1.0, 0.0] for t in texts]

    return embed


async def test_embeddings_are_computed_once_and_cached_on_disk(tmp_path: Path) -> None:
    news = {f"N{i}": NewsItem(f"N{i}", "news", "world", f"Title {i}", "") for i in range(150)}
    calls: list[int] = []
    store = EmbeddingStore(
        tmp_path / "c.sqlite", model="e", dimensions=3, embed=fake_embedder(calls)
    )

    await store.ensure(news, list(news))
    await store.ensure(news, list(news))
    again = EmbeddingStore(
        tmp_path / "c.sqlite", model="e", dimensions=3, embed=fake_embedder(calls)
    )
    await again.ensure(news, list(news))

    assert calls == [100, 50]  # batched, then never again
    assert np.allclose(np.linalg.norm(again.vectors(["N1", "N2"]), axis=1), 1.0)


async def test_another_model_or_size_is_a_separate_cache_entry(tmp_path: Path) -> None:
    news = {"N1": NewsItem("N1", "news", "world", "Title", "")}
    calls: list[int] = []
    for model, dims in (("e", 3), ("e", 3), ("e2", 3), ("e", 4)):
        store = EmbeddingStore(
            tmp_path / "c.sqlite", model=model, dimensions=dims, embed=fake_embedder(calls)
        )
        await store.ensure(news, ["N1"])

    assert len(calls) == 3


async def test_arm_c_only_sees_clicks_from_before_the_impression(sample_source: DataSource) -> None:
    news = load_news(sample_source.dev_dir / "news.tsv")
    impression = make_impression(history=0)
    impression = type(impression)(
        impression.impression_id,
        impression.user_id,
        impression.time,
        history=tuple(list(news)[:15]),
        shown=tuple((news_id, i % 2) for i, news_id in enumerate(list(news)[20:30])),
    )
    candidates = build_candidate_set(impression, seed=1, max_candidates=8, max_clicked=2)
    resources = ArmResources(retriever=Retriever(news, None))

    knowledge = await ARM_SPECS["C"].prepare(candidates, resources)

    memories = knowledge["memories"]
    assert isinstance(memories, list)
    assert {m["news_id"] for m in memories} <= set(impression.history)
    assert not {m["news_id"] for m in memories} & set(candidates.items)
    assert knowledge["retrieval"] == "tfidf"


def test_arm_c_prompt_lists_memories_but_no_reasons_or_labels() -> None:
    candidates = build_candidate_set(make_impression(), seed=1, max_candidates=8, max_clicked=2)
    news = {i: NewsItem(i, "sports", "nfl", f"Headline {i}", "") for i in candidates.items}
    knowledge = {
        "memories": [
            {"news_id": "H1", "headline": "Old click", "category": "sports", "reason": "recent"}
        ]
    }

    messages = ARM_SPECS["C"].render(candidates, news, knowledge, base_rate_hint=False)

    system = messages[0]["content"]
    assert "- [sports] Old click" in system
    assert "recent" not in system
    assert "similar to" not in system
    assert 'clicked": 1' not in messages[1]["content"]


@pytest.mark.parametrize("arms", [["C"], ["A", "C"]])
async def test_arm_c_runs_in_mock_mode_without_calling_embeddings(
    sample_source: DataSource, tmp_path: Path, arms: list[str]
) -> None:
    calls: list[int] = []
    store = EmbeddingStore(
        tmp_path / "c.sqlite", model="e", dimensions=3, embed=fake_embedder(calls)
    )
    client = LLMClient(
        model="mock",
        base_url="mock://",
        cache=Cache(tmp_path / "c.sqlite"),
        backend=mock_backend,
        concurrency=4,
    )

    run = await run_experiment(
        sample_source,
        ExperimentConfig(n_dev=10, n_test=20),
        population="dev",
        arms=arms,
        client=client,
        options=LLMOptions("medium", 4096, base_rate_hint=False, embed_model="e"),
        embeddings=store,
    )

    c_users = [u for u in run.users if u.arm == "C"]
    assert calls == []
    assert run.retrieval == "tfidf"
    assert len(c_users) == 10
    assert all(u.knowledge["memories"] for u in c_users)
    assert all(not u.knowledge for u in run.users if u.arm == "A")
