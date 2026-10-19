"""run-typecheck gate: basedpyright (backend), tsc -b via `npm run typecheck` (frontend)."""

from __future__ import annotations

import json
import sys

from _harness import FRONTEND, Check, Failure, parse_args, regex_parser, run_checks


def parse_basedpyright(out: str) -> list[Failure]:
    """Errors from `basedpyright --outputjson`; warnings don't fail the gate."""
    start = out.find("{")
    if start < 0:
        return []
    try:
        report = json.loads(out[start:])
    except json.JSONDecodeError:
        return []
    return [
        Failure(
            d["file"],
            d["range"]["start"]["line"] + 1,
            d["message"],
            {"rule": d["rule"]} if d.get("rule") else {},
        )
        for d in report.get("generalDiagnostics", [])
        if d.get("severity") == "error"
    ]


CHECKS = [
    Check(
        "backend", "basedpyright", ["uv", "run", "basedpyright", "--outputjson"], parse_basedpyright
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
