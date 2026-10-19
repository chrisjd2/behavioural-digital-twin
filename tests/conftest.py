from pathlib import Path

import pytest

from backend.data import DataSource, resolve_data_source
from backend.sample import write_synthetic_sample


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("data")
    write_synthetic_sample(directory / "sample", n_users=400, n_news=300, seed=1)
    return directory


@pytest.fixture(scope="session")
def sample_dir(data_dir: Path) -> Path:
    return data_dir / "sample"


@pytest.fixture(scope="session")
def sample_source(data_dir: Path) -> DataSource:
    return resolve_data_source(data_dir)
