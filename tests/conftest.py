from pathlib import Path

import pytest

from backend.sample import write_synthetic_sample


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("sample")
    write_synthetic_sample(directory, n_users=400, n_news=300, seed=1)
    return directory
