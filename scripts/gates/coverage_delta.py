"""coverage-delta gate: coverage of changed backend Python lines vs --base, per file.

Fails any changed file under GATE_COVERAGE_MIN (default 80%) of its changed executable lines.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from _harness import Failure, emit, git, parse_args, parse_pytest, run, tail

GATE = "coverage-delta"
HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


class GateError(Exception):
    def __init__(self, code: int, summary: str, failures: list[Failure] | None = None) -> None:
        super().__init__(summary)
        self.code, self.summary, self.failures = code, summary, failures


def threshold() -> float:
    raw = os.environ.get("GATE_COVERAGE_MIN", "80")
    try:
        value = float(raw.rstrip("%"))
    except ValueError:
        raise GateError(2, f"harness error: GATE_COVERAGE_MIN={raw!r} is not a number") from None
    return value / 100 if value > 1 else value


def changed_lines(base: str) -> dict[str, set[int]]:
    """Added/modified lines per backend .py file, working tree vs merge-base with `base`."""
    merge_base = git("merge-base", "HEAD", base)
    names = git("diff", "--name-only", "--diff-filter=AM", merge_base, "--", "backend").split()
    result: dict[str, set[int]] = {}
    for name in names:
        if not name.endswith(".py") or name.endswith("__init__.py"):
            continue
        lines: set[int] = set()
        for m in HUNK.finditer(git("diff", "-U0", merge_base, "--", name)):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            lines.update(range(start, start + count))
        if lines:
            result[name] = lines
    return result


def ranges(lines: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for n in lines:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def coverage_report() -> dict[str, Any]:
    """Run pytest under coverage; return coverage.py's per-file JSON keyed by posix path."""
    code, out = run(["uv", "run", "coverage", "run", "-m", "pytest", "-q", "--no-header"])
    if code != 0:
        failed = parse_pytest(out)
        if failed:
            for f in failed:
                f.extra["tool"] = "pytest"
            raise GateError(1, f"{len(failed)} test(s) failed under coverage", failed)
        raise GateError(2, f"harness error: coverage run failed: {tail(out)}")
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "coverage.json"
        code, out = run(["uv", "run", "coverage", "json", "-q", "-o", str(report)])
        if code != 0:
            raise GateError(2, f"harness error: coverage json failed: {tail(out)}")
        files = json.loads(report.read_text(encoding="utf-8"))["files"]
    return {k.replace("\\", "/"): v for k, v in files.items()}


def check_file(name: str, lines: set[int], data: dict[str, Any], minimum: float) -> Failure | None:
    executed = set(data["executed_lines"])
    executable = lines & (executed | set(data["missing_lines"]))
    covered = executable & executed
    if not executable or len(covered) / len(executable) >= minimum:
        return None
    pct = len(covered) / len(executable)
    uncovered = sorted(executable - covered)
    return Failure(
        name,
        uncovered[0],
        f"{pct:.0%} of changed lines covered (threshold {minimum:.0%})",
        {
            "changed_lines": len(executable),
            "covered_lines": len(covered),
            "coverage_pct": round(pct, 3),
            "threshold": minimum,
            "uncovered_ranges": ranges(uncovered),
            "tool": "coverage",
        },
    )


def measure(base: str) -> tuple[str, list[Failure]]:
    minimum = threshold()
    try:
        changed = changed_lines(base)
    except RuntimeError as exc:
        raise GateError(2, f"harness error: {exc}") from exc
    if not changed:
        return "no-op: no backend Python changed", []
    measured = coverage_report()
    failures = []
    for name, lines in sorted(changed.items()):
        # A changed file no test imports is entirely uncovered.
        data = measured.get(name, {"executed_lines": [], "missing_lines": sorted(lines)})
        failure = check_file(name, lines, data, minimum)
        if failure:
            failures.append(failure)
    return f"backend: {len(changed)} changed file(s), {len(failures)} below {minimum:.0%}", failures


def main(argv: list[str]) -> int:
    args = parse_args(argv, with_base=True)
    if "backend" not in args.tree:
        code, summary, failures = 0, "no-op: only backend is measured", []
    else:
        try:
            summary, failures = measure(args.base)
            code = 1 if failures else 0
        except GateError as err:
            code, summary, failures = err.code, err.summary, err.failures
        except Exception as exc:  # an unexpected crash is still an envelope, never a traceback
            code, summary, failures = 2, f"harness error: {exc!r}", []
    return emit(
        GATE,
        trees=["backend"] if "backend" in args.tree else args.tree,
        exit_code=code,
        summary=summary,
        failures=failures,
        issue=args.issue,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
