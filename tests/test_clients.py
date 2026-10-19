"""build_llm: the client and embedding store headless and live runs share. Nothing is called."""

from pathlib import Path

from backend.clients import build_llm
from backend.llm import mock_backend
from tests.test_status import make_settings


def test_mock_mode_uses_the_mock_backend_and_no_embeddings(tmp_path: Path) -> None:
    client, embeddings = build_llm(
        make_settings(mock_llm=True, embed_model="text-embedding-004"), tmp_path / "cache.sqlite"
    )

    assert client.backend is mock_backend
    assert (client.model, client.base_url) == ("mock", "mock://")
    assert embeddings is None


def test_real_mode_uses_the_configured_model_and_embeddings(tmp_path: Path) -> None:
    settings = make_settings(
        mock_llm=False,
        llm_api_key="test-key",
        llm_base_url="https://llm.example/v1/",
        embed_model="text-embedding-004",
        embed_dimensions=256,
    )

    client, embeddings = build_llm(settings, tmp_path / "cache.sqlite")

    assert client.backend is not mock_backend
    assert (client.model, client.base_url) == ("gemini-test-001", "https://llm.example/v1/")
    assert embeddings is not None
    assert (embeddings.model, embeddings.dimensions) == ("text-embedding-004", 256)


def test_real_mode_without_an_embedding_model_uses_tfidf(tmp_path: Path) -> None:
    _, embeddings = build_llm(
        make_settings(mock_llm=False, llm_api_key="test-key"), tmp_path / "cache.sqlite"
    )

    assert embeddings is None
