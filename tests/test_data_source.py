import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.data import date_range, load_behaviors, resolve_data_source
from backend.main import build_app
from backend.sample import write_synthetic_sample
from scripts import download_mind
from tests.test_status import make_settings

BEHAVIORS = "1\tU1\t11/15/2019 9:00:00 AM\tN1\tN2-1 N3-0\n"


def write_split(directory: Path) -> None:
    directory.mkdir(parents=True)
    (directory / "behaviors.tsv").write_text(BEHAVIORS, encoding="utf-8")
    (directory / "news.tsv").write_text("N1\tnews\tworld\tT\tA\t\t[]\t[]\n", encoding="utf-8")


def test_resolves_real_mind_before_synthetic(tmp_path: Path) -> None:
    write_split(tmp_path / "mind" / "dev")
    write_split(tmp_path / "mind" / "train")
    write_synthetic_sample(tmp_path / "sample", n_users=20, n_news=30, seed=1)

    source = resolve_data_source(tmp_path)

    assert source.kind == "mind"
    assert source.dev_dir == tmp_path / "mind" / "dev"
    assert source.train_dir == tmp_path / "mind" / "train"


def test_falls_back_to_synthetic_then_none(tmp_path: Path) -> None:
    assert resolve_data_source(tmp_path).kind == "none"

    write_synthetic_sample(tmp_path / "sample", n_users=20, n_news=30, seed=1)

    assert resolve_data_source(tmp_path).kind == "synthetic"


def test_synthetic_train_split_is_strictly_before_dev(tmp_path: Path) -> None:
    write_synthetic_sample(tmp_path, n_users=50, n_news=60, seed=1)

    dev = date_range(load_behaviors(tmp_path / "dev" / "behaviors.tsv"))
    train = date_range(load_behaviors(tmp_path / "train" / "behaviors.tsv"))

    assert train[1] < dev[0]
    assert dev[0].date() == dev[1].date()


def test_status_reports_detected_data_source(tmp_path: Path) -> None:
    write_synthetic_sample(tmp_path / "sample", n_users=20, n_news=30, seed=1)
    client = TestClient(build_app(make_settings(data_dir=str(tmp_path))))

    assert client.get("/api/status").json()["data_source"] == "synthetic"


def fake_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("behaviors.tsv", BEHAVIORS)
        archive.writestr("news.tsv", "N1\tnews\tworld\tT\tA\t\t[]\t[]\n")


def test_download_unpacks_both_splits_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched: list[str] = []

    def fetch(url: str, destination: Path, token: str) -> None:
        assert token == "hf_test"
        fetched.append(url.rsplit("/", 1)[1])
        fake_zip(destination)

    monkeypatch.setattr(download_mind, "fetch", fetch)

    download_mind.download(tmp_path / "mind", token="hf_test")
    download_mind.download(tmp_path / "mind", token="hf_test")

    assert sorted(fetched) == ["MINDsmall_dev.zip", "MINDsmall_train.zip"]
    for split in ("dev", "train"):
        assert (tmp_path / "mind" / split / "behaviors.tsv").exists()
    assert resolve_data_source(tmp_path).kind == "mind"


def test_download_without_token_explains_how_to_get_one(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="HF_TOKEN"):
        download_mind.download(tmp_path / "mind", token="")


def test_data_dir_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "data/mind/dev/behaviors.tsv"], check=False
    )
    assert result.returncode == 0
