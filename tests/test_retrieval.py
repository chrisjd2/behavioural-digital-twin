import dataclasses
from pathlib import Path

import numpy as np
import pytest

from backend.arms import ARM_SPECS, ArmResources, LLMOptions
from backend.data import DataSource, NewsItem, build_candidate_set, load_news
from backend.experiment import ExperimentConfig
from backend.llm import Cache, LLMClient, mock_backend
from backend.retrieval import MAX_MEMORIES, EmbeddingStore, Retriever, TfidfIndex, select_memories
from backend.runner import check_embeddings, run_experiment
from tests.factories import make_impression

NEWS = {f"H{i}": NewsItem(f"H{i}", "sports", "nfl", f"History {i}", "") for i in range(30)} | {
    f"C{i}": NewsItem(f"C{i}", "sports", "nfl", f"Candidate {i}", "") for i in range(8)
}
CANDIDATES = [f"C{i}" for i in range(8)]


def test_recent_first_then_best_matches_with_reasons() -> None:
    history = ["H0", "H1", "H2", "H3", "H4"]
    similarity = np.array([[0.9, 0.8, 0.7, 0.1, 0.0]])  # one candidate: H0 > H1 > H2

    memories = select_memories(history, ["C0"], similarity, NEWS)

    assert [m.news_id for m in memories] == ["H4", "H3", "H2", "H0", "H1"]
    assert [m.reason for m in memories[:3]] == ["recent"] * 3  # H2 is recent and similar
    assert memories[3].reason == "similar to: Candidate 0"
    assert memories[3].category == "sports/nfl"


def test_every_candidate_gets_a_tailored_memory_before_any_gets_a_second() -> None:
    history = [f"H{i}" for i in range(30)]
    similarity = np.zeros((8, 30))
    for row in range(8):  # candidate k's best match is H(3k), then H(3k+1), H(3k+2)
        similarity[row, 3 * row : 3 * row + 3] = [0.9, 0.8, 0.7]

    memories = select_memories(history, CANDIDATES, similarity, NEWS)

    reasons = [m.reason for m in memories]
    assert len(memories) == MAX_MEMORIES
    for candidate in range(8):
        assert f"similar to: Candidate {candidate}" in reasons
    assert [m.news_id for m in memories[:3]] == ["H29", "H28", "H27"]


def test_duplicates_are_listed_once() -> None:
    history = [f"H{i}" for i in range(10)]
    same_order = np.tile(np.linspace(1, 0, 10), (2, 1))  # both candidates like H0, H1, H2

    memories = select_memories(history, ["C0", "C1"], same_order, NEWS)

    ids = [m.news_id for m in memories]
    assert len(ids) == len(set(ids)) == 6


def test_short_history_and_all_equal_similarities() -> None:
    memories = select_memories(["H0", "H1"], ["C0", "C1"], np.full((2, 2), 0.5), NEWS)

    assert [(m.news_id, m.reason) for m in memories] == [("H1", "recent"), ("H0", "recent")]


def test_a_candidate_already_clicked_is_never_a_memory() -> None:
    history = ["H0", "H1", "C0", "H2", "H3"]
    similarity = np.array([[0.0, 0.0, 1.0, 0.0, 0.0]])  # C0 matches itself perfectly

    memories = select_memories(history, ["C0"], similarity, NEWS)

    assert "C0" not in {m.news_id for m in memories}


def test_tfidf_prefers_shared_words() -> None:
    news = {
        "a": NewsItem("a", "sports", "nfl", "Patriots win playoff game", ""),
        "b": NewsItem("b", "sports", "nfl", "Patriots playoff hopes", ""),
        "c": NewsItem("c", "food", "recipes", "Easy pumpkin pie", ""),
    }

    similarity = TfidfIndex(news).similarity(["a"], ["b", "c"])

    assert similarity[0, 0] > similarity[0, 1]


def fake_embedder(calls: list[int]):
    async def embed(texts: list[str]) -> list[list[float]]:
        calls.append(len(texts))
        return [[float(len(t)), 1.0, 0.0] for t in texts]

    return embed


def store(path: Path, calls: list[int], *, base_url: str = "u", model: str = "e", dims: int = 3):
    return EmbeddingStore(
        path, base_url=base_url, model=model, dimensions=dims, embed=fake_embedder(calls)
    )


async def test_embeddings_are_computed_once_and_cached_on_disk(tmp_path: Path) -> None:
    news = {f"N{i}": NewsItem(f"N{i}", "news", "world", f"Title {i}", "") for i in range(150)}
    calls: list[int] = []

    first = store(tmp_path / "c.sqlite", calls)
    await first.ensure(news, list(news))
    await first.ensure(news, list(news))
    again = store(tmp_path / "c.sqlite", calls)
    await again.ensure(news, list(news))

    assert calls == [100, 50]  # batched, then never again
    assert again.similarity(["N1"], ["N1"])[0, 0] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "other", [{"model": "e2"}, {"dims": 4}, {"base_url": "https://elsewhere/"}]
)
async def test_another_endpoint_model_or_size_is_a_separate_cache_entry(
    tmp_path: Path, other: dict[str, object]
) -> None:
    news = {"N1": NewsItem("N1", "news", "world", "Title", "")}
    calls: list[int] = []

    await store(tmp_path / "c.sqlite", calls).ensure(news, ["N1"])
    await store(tmp_path / "c.sqlite", calls, **other).ensure(news, ["N1"])  # type: ignore[arg-type]

    assert len(calls) == 2


def test_the_store_must_match_the_embedding_options(tmp_path: Path) -> None:
    options = LLMOptions("medium", 4096, base_rate_hint=False, embed_model="e", embed_dimensions=3)
    matching = store(tmp_path / "c.sqlite", [], base_url="u")

    check_embeddings(options, matching, base_url="u")
    with pytest.raises(ValueError, match="no embedding store"):
        check_embeddings(options, None, base_url="u")
    with pytest.raises(ValueError, match="does not match"):
        check_embeddings(options, store(tmp_path / "c.sqlite", [], dims=4), base_url="u")
    with pytest.raises(ValueError, match="EMBED_MODEL is empty"):
        check_embeddings(dataclasses.replace(options, embed_model=""), matching, base_url="u")


async def test_memories_come_only_from_the_users_own_earlier_clicks(
    sample_source: DataSource,
) -> None:
    news = load_news(sample_source.dev_dir / "news.tsv")
    ids = list(news)
    impression = dataclasses.replace(
        make_impression(),
        history=tuple(ids[:15]),
        shown=tuple((news_id, i % 2) for i, news_id in enumerate(ids[20:30])),
    )
    candidates = build_candidate_set(impression, seed=1, max_candidates=8, max_clicked=2)
    resources = ArmResources(retriever=Retriever(news, None))

    knowledge = await ARM_SPECS["C"].prepare(candidates, resources)

    assert candidates.history == impression.history
    memories = knowledge["memories"]
    assert isinstance(memories, list)
    assert memories
    assert {m["news_id"] for m in memories} <= set(impression.history)


def test_arm_c_prompt_lists_memories_but_no_reasons_or_labels() -> None:
    candidates = build_candidate_set(make_impression(), seed=1, max_candidates=8, max_clicked=2)
    news = {i: NewsItem(i, "sports", "nfl", f"Headline {i}", "") for i in candidates.items}
    knowledge = {
        "memories": [
            {"news_id": "H1", "headline": "Old click", "category": "sports/nfl", "reason": "recent"}
        ]
    }

    messages = ARM_SPECS["C"].render(candidates, news, knowledge, base_rate_hint=False)

    prompt = " ".join(m["content"] for m in messages)
    assert "- [sports/nfl] Old click" in messages[0]["content"]
    for leak in ("recent", "similar to", '"clicked"', '"label"', '"labels"'):
        assert leak not in prompt.lower()


@pytest.mark.parametrize("arms", [["C"], ["A", "C"]])
async def test_arm_c_runs_in_mock_mode_without_calling_embeddings(
    sample_source: DataSource, tmp_path: Path, arms: list[str]
) -> None:
    calls: list[int] = []
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
        embeddings=store(tmp_path / "c.sqlite", calls),
    )

    c_users = [u for u in run.users if u.arm == "C"]
    assert calls == []
    assert run.retrieval == "tfidf"
    assert len(c_users) == 10
    assert all(u.knowledge["memories"] for u in c_users)
    assert all(u.history for u in run.users)
    assert all(not u.knowledge for u in run.users if u.arm == "A")
