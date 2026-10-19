"""Write the synthetic (fake) MIND-format sample to data/sample/ for offline development.

uv run python -m scripts.make_sample
"""

import sys
from pathlib import Path

from backend.sample import write_synthetic_sample


def main() -> int:
    target = Path("data/sample")
    write_synthetic_sample(target, n_users=800, n_news=400, seed=1)
    print(f"Wrote synthetic sample to {target}/ (fake data, for development and tests only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
