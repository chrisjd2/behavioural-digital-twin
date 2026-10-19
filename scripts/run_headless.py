"""Run the experiment from the command line and print the metrics table.

uv run python -m scripts.run_headless --population dev --arms random
"""

import argparse
import statistics
import sys
from pathlib import Path

from backend.data import date_range, load_behaviors, resolve_data_source
from backend.experiment import ExperimentConfig, evaluate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--population", choices=["dev", "test"], default="dev")
    parser.add_argument("--arms", default="random", help="Comma-separated, e.g. random")
    parser.add_argument("--n-dev", type=int, default=ExperimentConfig.n_dev)
    parser.add_argument("--n-test", type=int, default=ExperimentConfig.n_test)
    args = parser.parse_args(argv)

    config = ExperimentConfig(n_dev=args.n_dev, n_test=args.n_test)
    source = resolve_data_source(args.data_dir)
    if source.kind == "none":
        print(f"No data in {args.data_dir}: run scripts.download_mind or scripts.make_sample")
        return 2
    results = evaluate(source, config, population=args.population, arms=args.arms.split(","))

    label = "SYNTHETIC SAMPLE (fake data)" if source.kind == "synthetic" else "MIND-small"
    print(f"Data: {label} ({source.root}) | population: {args.population}")
    for split, directory in (("train", source.train_dir), ("dev", source.dev_dir)):
        start, end = date_range(load_behaviors(directory / "behaviors.tsv"))
        print(f"  {split} impressions: {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M}")
    print(f"{'arm':<10} {'users':>6} {'mean AUC':>9}")
    for arm, aucs in results.items():
        print(f"{arm:<10} {len(aucs):>6} {statistics.fmean(aucs):>9.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
