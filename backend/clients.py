"""The LLM client and embedding store a run uses, built from settings (headless and live runs)."""

from pathlib import Path

from backend.config import Settings
from backend.llm import Cache, LLMClient, mock_backend, openai_backend, openai_embedder
from backend.retrieval import EmbeddingStore


def build_llm(settings: Settings, cache_path: Path) -> tuple[LLMClient, EmbeddingStore | None]:
    """Mock mode needs no key and never embeds (runs use TF-IDF, ADR-0006)."""
    if settings.mock_llm:
        backend, model, base_url = mock_backend, "mock", "mock://"
    else:
        backend = openai_backend(settings.llm_base_url, settings.llm_api_key)
        model, base_url = settings.llm_model, settings.llm_base_url
    client = LLMClient(
        model=model,
        base_url=base_url,
        cache=Cache(cache_path),
        backend=backend,
        concurrency=settings.concurrency,
    )
    options = settings.llm_options()
    if settings.mock_llm or not options.embed_model:
        return client, None
    return client, EmbeddingStore(
        cache_path,
        base_url=settings.llm_base_url,
        model=options.embed_model,
        dimensions=options.embed_dimensions,
        embed=openai_embedder(
            settings.llm_base_url,
            settings.llm_api_key,
            model=options.embed_model,
            dimensions=options.embed_dimensions,
        ),
    )
