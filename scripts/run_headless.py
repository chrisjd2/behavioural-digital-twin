"""Run the experiment from the command line and print the metrics table.

uv run python -m scripts.run_headless --population dev --arms random
"""

import argparse
import sys
from pathlib import Path

from backend.experiment import ExperimentConfig, evaluate
from backend.report import Estimate, Report, build_report
from backend.sample import is_synthetic

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
    parser.add_argument("--data-dir", type=Path, default=Path("data/sample"))
    parser.add_argument("--population", choices=["dev", "test"], default="dev")
    parser.add_argument("--arms", default="random", help="Comma-separated, e.g. random")
    parser.add_argument("--n-dev", type=int, default=ExperimentConfig.n_dev)
    parser.add_argument("--n-test", type=int, default=ExperimentConfig.n_test)
    args = parser.parse_args(argv)

    config = ExperimentConfig(n_dev=args.n_dev, n_test=args.n_test)
    results = evaluate(args.data_dir, config, population=args.population, arms=args.arms.split(","))

    source = "SYNTHETIC SAMPLE (fake data)" if is_synthetic(args.data_dir) else str(args.data_dir)
    print(f"Data: {source} | population: {args.population}")
    print(format_report(build_report(results)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
