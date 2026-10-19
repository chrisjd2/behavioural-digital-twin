from pathlib import Path

import pytest

from backend.config import get_settings
from backend.data import DataSource, resolve_data_source
from backend.sample import write_synthetic_sample


@pytest.fixture(autouse=True)
def force_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests see the same settings as CI, whatever a local .env says (env vars beat .env)."""
    monkeypatch.setenv("MOCK_LLM", "true")
    for name in ("LLM_API_KEY", "LLM_MODEL", "EMBED_MODEL", "HF_TOKEN"):
        monkeypatch.setenv(name, "")
    for name in ("LLM_REASONING_EFFORT", "LLM_MAX_OUTPUT_TOKENS", "EMBED_DIMENSIONS", "DEMO_MODE"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("data")
    write_synthetic_sample(directory / "sample", n_users=600, n_news=300, seed=1)
    return directory


@pytest.fixture(scope="session")
def sample_dir(data_dir: Path) -> Path:
    return data_dir / "sample"


@pytest.fixture(scope="session")
def sample_source(data_dir: Path) -> DataSource:
    return resolve_data_source(data_dir)
