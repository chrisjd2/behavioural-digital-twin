"""Run the experiment from the command line, print the metrics table and save the run file.

uv run python -m scripts.run_headless --population dev --arms A,random
"""

import argparse
import asyncio
import sys
from pathlib import Path

from backend.config import Settings, get_settings
from backend.data import date_range, load_behaviors, resolve_data_source
from backend.experiment import ExperimentConfig
from backend.freeze import freeze_problem
from backend.llm import Backend, Cache, LLMClient, mock_backend, openai_backend
from backend.runner import LLM_ARMS, RunEvent, run_experiment
from backend.runs import save_run

RUNS_SUBDIR = Path("runs")
CACHE_FILE = Path("cache.sqlite")


def make_backend(settings: Settings) -> Backend:
    return openai_backend(settings.llm_base_url, settings.llm_api_key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None, help="Defaults to DATA_DIR")
    parser.add_argument("--population", choices=["dev", "test"], default="dev")
    parser.add_argument("--arms", default="random", help="Comma-separated, e.g. A,random")
    parser.add_argument("--n-dev", type=int, default=ExperimentConfig.n_dev)
    parser.add_argument("--n-test", type=int, default=ExperimentConfig.n_test)
    parser.add_argument(
        "--allow-unfrozen", action="store_true", help="Run the test set without the freeze tag"
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    data_dir = args.data_dir or Path(settings.data_dir)
    arms = args.arms.split(",")

    source = resolve_data_source(data_dir)
    if source.kind == "none":
        print(f"No data in {data_dir}: run scripts.download_mind or scripts.make_sample")
        return 2

    uses_llm = any(arm in LLM_ARMS for arm in arms)
    if args.population == "test" and uses_llm and not args.allow_unfrozen:
        problem = freeze_problem()
        if problem:
            print(f"Refusing to run the test set: {problem} (ADR-0001).")
            return 3

    if settings.mock_llm:
        backend, model, base_url = mock_backend, "mock", "mock://"
    else:
        if uses_llm and not (settings.llm_model and settings.llm_api_key):
            print("Set LLM_MODEL and LLM_API_KEY in .env, or MOCK_LLM=true.")
            return 2
        backend, model, base_url = make_backend(settings), settings.llm_model, settings.llm_base_url
    client = LLMClient(
        model=model,
        base_url=base_url,
        cache=Cache(data_dir / CACHE_FILE),
        backend=backend,
        concurrency=settings.concurrency,
    )

    def progress(event: RunEvent) -> None:
        if event.kind == "arm_progress":
            data = event.data
            print(f"\r  {data['arm']}: {data['done']}/{data['total']}", end="", flush=True)

    config = ExperimentConfig(n_dev=args.n_dev, n_test=args.n_test)
    run = asyncio.run(
        run_experiment(
            source,
            config,
            population=args.population,
            arms=arms,
            client=client,
            base_rate_hint=settings.base_rate_hint,
            on_event=progress,
        )
    )
    run.unfrozen_override = args.allow_unfrozen
    print()

    if run.mock and uses_llm:
        print("*** MOCK LLM OUTPUT: fake numbers for development, never results ***")
    label = "SYNTHETIC SAMPLE (fake data)" if source.kind == "synthetic" else "MIND-small"
    print(f"Data: {label} ({source.root}) | population: {args.population} | model: {run.model}")
    for split, directory in (("train", source.train_dir), ("dev", source.dev_dir)):
        start, end = date_range(load_behaviors(directory / "behaviors.tsv"))
        print(f"  {split} impressions: {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M}")
    print(f"{'arm':<10} {'users':>6} {'mean AUC':>9} {'parse fail':>11}")
    for arm, m in run.metrics.items():
        print(f"{arm:<10} {m['n']:>6.0f} {m['mean_auc']:>9.3f} {m['parse_failure_rate']:>11.1%}")
    c = run.counters
    print(f"LLM calls: {c['calls']} new, {c['cache_hits']} cached, {c['prompt_tokens']} tokens in")
    print(f"Saved {save_run(run, data_dir / RUNS_SUBDIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
