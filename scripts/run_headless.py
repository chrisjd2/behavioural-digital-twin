"""Run the experiment from the command line, print the report and save the run file.

uv run python -m scripts.run_headless --population dev --arms A,random
"""

import argparse
import asyncio
import sys
from pathlib import Path

from backend.config import get_settings
from backend.data import resolve_data_source
from backend.experiment import ExperimentConfig
from backend.llm import Cache, LLMClient, mock_backend, openai_backend, openai_embedder
from backend.report import Estimate, Report, build_report
from backend.retrieval import EmbeddingStore
from backend.runner import LLM_ARMS, FreezeError, Run, RunEvent, run_experiment
from backend.runs import save_run

RUNS_SUBDIR = Path("runs")
CACHE_FILE = Path("cache.sqlite")
METRIC_LABELS = {"auc": "AUC", "mrr": "MRR", "ndcg5": "nDCG@5", "hit1": "Hit@1"}


def _ci(e: Estimate, sign: str = "") -> str:
    return f"{e.mean:{sign}.3f} [{e.low:{sign}.3f}, {e.high:{sign}.3f}]"


def format_report(report: Report) -> str:
    header = f"{'arm':<8} {'n':>4}  " + "  ".join(f"{m:<20}" for m in METRIC_LABELS.values())
    lines = ["Per-arm means [95% bootstrap CI]", header + f"  {'ties':>6} {'parse fail':>10}"]
    for s in report.arms.values():
        cells = "  ".join(f"{_ci(s.metrics[m]):<20}" for m in METRIC_LABELS)
        lines.append(
            f"{s.arm:<8} {s.n:>4}  {cells}  {s.tie_share:>6.1%} {s.parse_failure_rate:>10.1%}"
        )

    lines += ["", "Calibration: mean p_click | feed CTR | sample CTR (inflated by design)"]
    for s in report.arms.values():
        c = s.calibration
        lines.append(
            f"{s.arm:<8} {c.mean_p_click:.3f} | {c.feed_ctr:.3f} | {c.sample_ctr:.3f}"
            if c
            else f"{s.arm:<8} n/a (baseline scores are not probabilities)"
        )

    if report.differences:
        lines += ["", "Paired AUC differences (mean [95% CI])"]
        lines += [f"{d.arm} - {d.reference:<6} {_ci(d.auc, '+')}" for d in report.differences]

    if p := report.primary:
        buckets = " | ".join(f"{name}: {count}" for name, count in p.buckets.items())
        lines += [
            "",
            f"Primary outcome, D - A AUC {_ci(p.difference, '+')}: {p.verdict}",
            f"Outcome buckets: {buckets}",
            f"Median user: {p.median_user}",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None, help="Defaults to DATA_DIR")
    parser.add_argument("--population", choices=["dev", "test"], default="dev")
    parser.add_argument("--arms", default="random", help="Comma-separated, e.g. A,random")
    parser.add_argument("--n-dev", type=int, default=ExperimentConfig.n_dev)
    parser.add_argument("--n-test", type=int, default=ExperimentConfig.n_test)
    parser.add_argument(
        "--allow-unfrozen", action="store_true", help="Run the test set without the freeze"
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    data_dir = args.data_dir or Path(settings.data_dir)
    arms = args.arms.split(",")
    uses_llm = any(arm in LLM_ARMS for arm in arms)

    source = resolve_data_source(data_dir)
    if source.kind == "none":
        print(f"No data in {data_dir}: run scripts.download_mind or scripts.make_sample")
        return 2

    if settings.mock_llm:
        backend, model, base_url = mock_backend, "mock", "mock://"
    else:
        if uses_llm and not (settings.llm_model and settings.llm_api_key):
            print("Set LLM_MODEL and LLM_API_KEY in .env, or MOCK_LLM=true.")
            return 2
        backend = openai_backend(settings.llm_base_url, settings.llm_api_key)
        model, base_url = settings.llm_model, settings.llm_base_url
    client = LLMClient(
        model=model,
        base_url=base_url,
        cache=Cache(data_dir / CACHE_FILE),
        backend=backend,
        concurrency=settings.concurrency,
    )
    options = settings.llm_options()
    embeddings = None
    if not settings.mock_llm and options.embed_model:
        embeddings = EmbeddingStore(
            data_dir / CACHE_FILE,
            model=options.embed_model,
            dimensions=options.embed_dimensions,
            embed=openai_embedder(
                settings.llm_base_url,
                settings.llm_api_key,
                model=options.embed_model,
                dimensions=options.embed_dimensions,
            ),
        )

    def progress(event: RunEvent) -> None:
        if event.kind == "arm_progress":
            data = event.data
            print(f"\r  {data['arm']}: {data['done']}/{data['total']}", end="", flush=True)

    config = ExperimentConfig(n_dev=args.n_dev, n_test=args.n_test)
    try:
        run = asyncio.run(
            run_experiment(
                source,
                config,
                population=args.population,
                arms=arms,
                client=client,
                options=options,
                embeddings=embeddings,
                allow_unfrozen=args.allow_unfrozen,
                on_event=progress,
            )
        )
    except FreezeError as e:
        print(e)
        return 3
    print()
    print_run(run, uses_llm=uses_llm)
    print(f"Saved {save_run(run, data_dir / RUNS_SUBDIR)}")
    return 0


def print_run(run: Run, *, uses_llm: bool) -> None:
    if run.mock and uses_llm:
        print("*** MOCK LLM OUTPUT: fake numbers for development, never results ***")
    if not run.is_result:
        print("NOT A RESULT: only the frozen test run on real MIND with a real model counts.")
    label = "SYNTHETIC SAMPLE (fake data)" if run.data_source == "synthetic" else "MIND-small"
    print(f"Data: {label} | population: {run.population} | model: {run.model}")
    print(f"  retrieval: {run.retrieval} | thinking: {run.options['reasoning_effort']}")
    for split, (start, end) in run.date_ranges.items():
        print(f"  {split} impressions: {start[:16]} to {end[:16]}")
    by_arm = {arm: [u for u in run.users if u.arm == arm] for arm in run.arms}
    seed = int(str(run.config["bootstrap_seed"]))
    print(format_report(build_report(by_arm, seed=seed)))
    c = run.counters
    print(
        f"\nLLM calls: {c['calls']} new, {c['cache_hits']} cached, {c['prompt_tokens']} tokens in"
    )
    for arm, screen in run.identity_screen.items():
        print(
            f"Identity screen, arm {arm}: {screen['flagged_profiles']}/{screen['profiles']} "
            f"profiles flagged ({screen['hits']} hits); {screen['unusable_profiles']} unusable"
        )
    if run.unfrozen_override:
        print("WARNING: test set run with --allow-unfrozen; recorded in the run file.")


if __name__ == "__main__":
    sys.exit(main())
