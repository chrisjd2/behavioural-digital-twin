"""List Step 0 Hook candidates from a dev run so a person can choose one (ADR-0008).

A candidate is a reader and a clicked/skipped headline pair where the plain LLM (arm A)
prefers the skipped headline, the full twin (arm D) the clicked one, and the reader's recent
clicks lean to the clicked headline's category. Test and result runs are refused: the hook
is illustrative, never evidence.

    uv run python -m scripts.pick_hook                 # newest dev run with arms A and D
    uv run python -m scripts.pick_hook --run <run_id>
    uv run python -m scripts.pick_hook --write 2       # save candidate 2 to config/hook.json
"""

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

from backend.config import get_settings
from backend.data import NewsItem
from backend.errors import AppError
from backend.hook import (
    HOOK_ARMS,
    HookCandidate,
    HookConfig,
    hook_candidates,
    is_illustrative,
    recent_history,
)
from backend.run_views import by_user, list_runs, open_run, run_news
from backend.runner import Run
from backend.runs import RUNS_SUBDIR


def newest_dev_run_id(runs_dir: Path) -> str | None:
    return next(
        (
            r.run_id
            for r in list_runs(runs_dir).runs
            if r.population == "dev" and not r.is_result and set(HOOK_ARMS) <= set(r.arms)
        ),
        None,
    )


def describe(rank: int, k: HookCandidate, run: Run, news: Mapping[str, NewsItem]) -> list[str]:
    def line(label: str, news_id: str) -> str:
        n = news.get(news_id)
        return f"   {label:<8} {f'[{n.category}/{n.subcategory}] {n.title}' if n else news_id}"

    history = recent_history(by_user(run)[k.user_id][0])
    return [
        f"{rank}. {k.user_id}: A prefers the skipped headline by {k.a_gap:g}, "
        f"D the clicked one by {k.d_gap:g}; recent clicks {k.history_hits} in the clicked "
        f"category, {k.history_misses} in the other's",
        line("clicked", k.clicked_id),
        line("skipped", k.other_id),
        *(line("history", i) for i in history),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None, help="Defaults to DATA_DIR")
    parser.add_argument("--run", default=None, help="Defaults to the newest dev run with A and D")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--config", type=Path, default=None, help="Defaults to HOOK_CONFIG")
    parser.add_argument("--write", type=int, default=None, help="Save candidate K to the config")
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.data_dir:
        settings = settings.model_copy(update={"data_dir": str(args.data_dir)})
    config_path: Path = args.config or Path(settings.hook_config)

    run_id = args.run or newest_dev_run_id(Path(settings.data_dir) / RUNS_SUBDIR)
    if run_id is None:
        print(f"No dev run with arms {' and '.join(HOOK_ARMS)} in {settings.data_dir}.")
        return 1
    try:
        run = open_run(settings, run_id)
        if not is_illustrative(run):
            print(f"Run {run_id} is not a dev run: the hook comes from the dev set only.")
            return 1
        news = run_news(settings, run)
    except AppError as exc:
        print(exc.detail)
        return 1

    candidates = hook_candidates(run, news)
    print(f"Run {run.run_id} ({run.population}, {run.model}): {len(candidates)} candidates")
    for rank, k in enumerate(candidates[: args.top], start=1):
        print("\n".join(describe(rank, k, run, news)))

    if args.write is not None:
        if not 1 <= args.write <= len(candidates):
            print(f"No candidate {args.write}.")
            return 1
        k = candidates[args.write - 1]
        chosen = HookConfig(
            run_id=run.run_id, user_id=k.user_id, clicked_id=k.clicked_id, other_id=k.other_id
        )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(chosen.model_dump(), indent=2) + "\n", encoding="utf-8")
        print(f"Wrote candidate {args.write} to {config_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
