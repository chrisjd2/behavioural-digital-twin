"""Assemble `demo-data/`, the hosted demo's DATA_DIR: what it shows and nothing else (ADR-0011).

- `runs/`: the frozen result run (the newest `is_result` run, or --run), the Step 0 Hook's
  dev run from HOOK_CONFIG, and the recorded interview's run from INTERVIEW_RECORDED if there
  is one. Copied byte for byte: a run file is never edited after it is made.
- `<mind|sample>/dev/news.tsv`: only the news items those runs mention, cut to the columns the
  app reads (id, category, subcategory, title, abstract). Every view finds headlines there
  (`backend.run_views.run_news`).
- `<mind|sample>/{dev,train}/behaviors.tsv`: empty. They keep `resolve_data_source`'s layout so
  `/api/status` labels the data; only population building and live runs read them, and
  DEMO_MODE refuses both.

No `cache.sqlite`: the interview never reads or writes the cache, and nothing else calls the
LLM in DEMO_MODE. No `.env` or keys: the key comes from Secret Manager at deploy time.
`demo-data/` is gitignored; it only ever goes into the private demo image.

    uv run python -m scripts.build_demo_data                  # into demo-data/
    uv run python -m scripts.build_demo_data --run <run_id> --out <dir>
"""

import argparse
import shutil
import sys
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path

from backend.config import Settings, get_settings
from backend.data import SYNTHETIC_MARKER, resolve_data_source
from backend.errors import AppError
from backend.hook import read_config
from backend.interview import read_recording
from backend.run_views import list_runs, open_run
from backend.runs import RUNS_SUBDIR

NEWS_COLUMNS = 5  # what `backend.data.load_news` reads


class DemoDataError(Exception):
    pass


def newest_result_run_id(runs_dir: Path) -> str | None:
    return next((r.run_id for r in list_runs(runs_dir).runs if r.is_result), None)


def demo_run_ids(settings: Settings, result_run: str | None) -> list[str]:
    """The result run, the hook's run and the recorded interview's run, without repeats."""
    run_id = result_run or newest_result_run_id(Path(settings.data_dir) / RUNS_SUBDIR)
    if run_id is None:
        raise DemoDataError(f"No result run in {settings.data_dir}; name one with --run.")
    ids = [run_id, read_config(Path(settings.hook_config)).run_id]
    recorded = Path(settings.interview_recorded)
    if recorded.is_file():
        ids.append(read_recording(recorded).run_id)
    else:
        print(f"No {recorded}: the demo's interview will have no recorded fallback.")
    return list(dict.fromkeys(ids))


def strings(value: object) -> Iterator[str]:
    """Every string in a run's JSON: ids sit in items, histories, knowledge and events."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from strings(v)


def build(settings: Settings, out: Path, result_run: str | None = None) -> list[Path]:
    """Write the demo DATA_DIR into `out` (which must not exist or be empty); its files."""
    if out.exists() and any(out.iterdir()):
        raise DemoDataError(f"{out} is not empty; remove it first.")
    runs = [open_run(settings, run_id) for run_id in demo_run_ids(settings, result_run)]
    source = resolve_data_source(Path(settings.data_dir))
    if source.kind == "none":
        raise DemoDataError(f"No MIND data or synthetic sample in {settings.data_dir}.")
    rows = {
        line.split("\t", 1)[0]: line.rstrip("\r")
        # Not splitlines: titles may hold U+2028, which the TSV reader keeps.
        for line in (source.dev_dir / "news.tsv").read_text(encoding="utf-8").split("\n")
        if line
    }

    needed: set[str] = set()
    for run in runs:
        if run.data_source != source.kind:
            raise DemoDataError(
                f"Run {run.run_id} used {run.data_source} data; {settings.data_dir} has "
                f"{source.kind}."
            )
        needed.update(s for s in strings(asdict(run)) if s in rows)

    root = out / source.root.name
    (root / "dev").mkdir(parents=True)
    (root / "train").mkdir()
    news = "".join("\t".join(rows[i].split("\t")[:NEWS_COLUMNS]) + "\n" for i in sorted(needed))
    (root / "dev" / "news.tsv").write_text(news, encoding="utf-8", newline="\n")
    for split in ("dev", "train"):
        (root / split / "behaviors.tsv").touch()
    if (source.root / SYNTHETIC_MARKER).exists():
        shutil.copy2(source.root / SYNTHETIC_MARKER, root / SYNTHETIC_MARKER)
    (out / RUNS_SUBDIR).mkdir()
    for run in runs:
        name = f"{run.run_id}.json"
        shutil.copy2(Path(settings.data_dir) / RUNS_SUBDIR / name, out / RUNS_SUBDIR / name)
    return sorted(p for p in out.rglob("*") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None, help="Defaults to DATA_DIR")
    parser.add_argument("--run", default=None, help="Defaults to the newest result run")
    parser.add_argument("--out", type=Path, default=Path("demo-data"))
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.data_dir:
        settings = settings.model_copy(update={"data_dir": str(args.data_dir)})
    try:
        files = build(settings, args.out, args.run)
    except (DemoDataError, AppError) as exc:
        print(exc.detail if isinstance(exc, AppError) else exc)
        return 1
    total = sum(f.stat().st_size for f in files)
    for f in files:
        print(f"{f.stat().st_size:>12,}  {f.relative_to(args.out).as_posix()}")
    print(f"{total:>12,}  {args.out} ({len(files)} files, {total / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
