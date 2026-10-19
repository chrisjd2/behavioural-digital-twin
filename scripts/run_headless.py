"""Run the experiment from the command line and print the metrics table.

uv run python -m scripts.run_headless --population dev --arms random
"""

import argparse
import statistics
import sys
from pathlib import Path

from backend.experiment import ExperimentConfig, evaluate


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

    titles = (args.data_dir / "news.tsv").read_text(encoding="utf-8")
    source = "SYNTHETIC SAMPLE (fake data)" if "[SYNTHETIC]" in titles else str(args.data_dir)
    print(f"Data: {source} | population: {args.population}")
    print(f"{'arm':<10} {'users':>6} {'mean AUC':>9}")
    for arm, aucs in results.items():
        print(f"{arm:<10} {len(aucs):>6} {statistics.fmean(aucs):>9.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
