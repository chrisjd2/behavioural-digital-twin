"""Download MIND-small dev and train into data/mind/{dev,train}/ (idempotent).

MIND is distributed for research use under the Microsoft Research License. The
official homepage (https://msnews.github.io) links to a gated Hugging Face copy:
  1. Sign in at https://huggingface.co/datasets/yjw1029/MIND and accept the terms.
  2. Create a read token at https://huggingface.co/settings/tokens.
  3. Put HF_TOKEN=hf_... in .env, then run:

    uv run python -m scripts.download_mind
"""

import sys
import urllib.request
import zipfile
from pathlib import Path

from backend.config import get_settings

BASE_URL = "https://huggingface.co/datasets/yjw1029/MIND/resolve/main"
SPLITS = {"dev": "MINDsmall_dev.zip", "train": "MINDsmall_train.zip"}
CHUNK = 1 << 20


def fetch(url: str, destination: Path, token: str) -> None:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request) as response, destination.open("wb") as out:
        total = int(response.headers.get("Content-Length", 0))
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {destination.name}: {done / total:6.1%}", end="", flush=True)
    print()


def flatten_single_folder(directory: Path) -> None:
    """The Hugging Face zips wrap their files in one folder (e.g. MINDsmall_dev/); lift them up."""
    entries = list(directory.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for item in inner.iterdir():
            item.rename(directory / item.name)
        inner.rmdir()


def download(target: Path, *, token: str) -> None:
    for split, filename in SPLITS.items():
        split_dir = target / split
        if (split_dir / "behaviors.tsv").exists() and (split_dir / "news.tsv").exists():
            print(f"{split}: already present in {split_dir}")
            continue
        if not token:
            sys.exit(f"{__doc__}\nHF_TOKEN is not set.")
        split_dir.mkdir(parents=True, exist_ok=True)
        archive = target / filename
        print(f"{split}: downloading {filename}")
        fetch(f"{BASE_URL}/{filename}", archive, token)
        with zipfile.ZipFile(archive) as z:
            z.extractall(split_dir)
        archive.unlink()
        flatten_single_folder(split_dir)
        if not (split_dir / "behaviors.tsv").exists():
            sys.exit(f"{filename} did not contain behaviors.tsv")
        print(f"{split}: unpacked to {split_dir}")


def main() -> int:
    settings = get_settings()
    download(Path(settings.data_dir) / "mind", token=settings.hf_token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
