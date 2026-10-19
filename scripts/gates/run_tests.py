"""run-tests gate: pytest (backend), Vitest via `npm run test` (frontend). No flake re-runs."""

from __future__ import annotations

import sys

from _harness import FRONTEND, Check, parse_args, parse_pytest, regex_parser, run_checks

CHECKS = [
    Check("backend", "pytest", ["uv", "run", "pytest", "-q", "--no-header"], parse_pytest),
    Check(
        "frontend",
        "vitest",
        ["npm", "run", "-s", "test"],
        regex_parser(r"^\s*FAIL\s+(?P<file>\S+\.tsx?)(?: > (?P<test>.+))?$", "test failed"),
        FRONTEND,
    ),
]


def main(argv: list[str]) -> int:
    return run_checks("run-tests", CHECKS, parse_args(argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
