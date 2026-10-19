"""run-typecheck gate: basedpyright (backend), tsc -b via `npm run typecheck` (frontend)."""

from __future__ import annotations

import sys

from _harness import FRONTEND, Check, parse_args, regex_parser, run_checks

CHECKS = [
    Check(
        "backend",
        "basedpyright",
        ["uv", "run", "basedpyright"],
        regex_parser(
            r"^\s*(?P<file>\S.*?\.pyi?):(?P<line>\d+):\d+ - error: (?P<msg>.+?)(?: \((?P<rule>\w+)\))?$"
        ),
    ),
    Check(
        "frontend",
        "tsc",
        ["npm", "run", "-s", "typecheck"],
        regex_parser(
            r"^(?P<file>[^\s(][^(]*)\((?P<line>\d+),\d+\): error (?P<rule>TS\d+): (?P<msg>.+)$"
        ),
        FRONTEND,
    ),
]


def main(argv: list[str]) -> int:
    return run_checks("run-typecheck", CHECKS, parse_args(argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
