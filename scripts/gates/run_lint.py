"""run-lint gate: ruff format/check (backend), oxlint + prettier (frontend). Never fixes."""

from __future__ import annotations

import sys

from _harness import FRONTEND, Check, parse_args, regex_parser, run_checks

CHECKS = [
    Check(
        "backend",
        "ruff format",
        ["uv", "run", "ruff", "format", "--check", "--output-format", "concise", "."],
        regex_parser(r"^(?P<file>[^\s:]+):(?P<line>\d+):\d+: unformatted: (?P<msg>.+)$"),
    ),
    Check(
        "backend",
        "ruff check",
        ["uv", "run", "ruff", "check", "--output-format", "concise", "."],
        regex_parser(r"^(?P<file>[^\s:]+):(?P<line>\d+):\d+: (?P<rule>[A-Z]+\d+) (?P<msg>.+)$"),
    ),
    Check(
        "frontend",
        "oxlint",
        ["npm", "run", "-s", "lint", "--", "--format", "unix"],
        regex_parser(
            r"^(?P<file>[^\s:]+):(?P<line>\d+):\d+: (?P<msg>.+?)(?: \[(?P<rule>[^\]]+)\])?$"
        ),
        FRONTEND,
    ),
    Check(
        "frontend",
        "prettier",
        ["npm", "run", "-s", "format:check"],
        regex_parser(r"^\[warn\] (?P<file>\S+)$", "file needs `npm run format`"),
        FRONTEND,
    ),
]


def main(argv: list[str]) -> int:
    return run_checks("run-lint", CHECKS, parse_args(argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
