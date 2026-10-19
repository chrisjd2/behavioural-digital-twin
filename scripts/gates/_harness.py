"""Shared plumbing for the gate scripts. Contract: .claude/skills/_shared/gate-protocol.md.

Exit codes: 0 pass, 1 failures, 2 a tool could not run or gave output we could not map.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
TREES = ("backend", "frontend")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class Failure:
    file: str
    line: int
    message: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "message": self.message, **self.extra}


Parser = Callable[[str], list[Failure]]


@dataclass
class Check:
    tree: str
    label: str
    cmd: list[str]
    parse: Parser
    cwd: Path = REPO_ROOT


def parse_args(argv: list[str], *, with_base: bool = False) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--tree", choices=TREES, action="append", help="limit to a tree (repeatable)")
    p.add_argument("--issue", type=int, help="cache envelope at .reviews/<N>/gates/<gate>.json")
    if with_base:
        p.add_argument("--base", default="origin/main", help="git ref to diff against")
    args = p.parse_args(argv)
    args.tree = args.tree or list(TREES)
    return args


def run(cmd: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str]:
    """Run a command; return (code, stdout+stderr). 127 when the executable is missing."""
    exe = shutil.which(cmd[0])
    if exe is None:
        return 127, f"{cmd[0]}: command not found"
    proc = subprocess.run(
        [exe, *cmd[1:]],
        check=False,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "NO_COLOR": "1", "FORCE_COLOR": "0"},
    )
    return proc.returncode, ANSI.sub("", proc.stdout + proc.stderr)


def git(*args: str) -> str:
    code, out = run(["git", *args])
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)}: {out.strip()}")
    return out.strip()


def tail(text: str, n: int = 15) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


def regex_parser(pattern: str, message: str = "") -> Parser:
    """Parser from a regex with named groups `file`, optional `line`/`msg`; others go to extra."""
    rx = re.compile(pattern, re.MULTILINE)

    def parse(out: str) -> list[Failure]:
        found = []
        for m in rx.finditer(out):
            g = {k: v.strip() for k, v in m.groupdict().items() if v}
            file = g.pop("file").replace("\\", "/")
            line = int(g.pop("line", 0))
            msg = g.pop("msg", message)
            found.append(Failure(file, line, msg, g))
        return found

    return parse


parse_pytest = regex_parser(
    r"^(?:FAILED|ERROR) (?P<file>[^:\s]+)(?:::(?P<test>\S+))?(?: - (?P<msg>.+))?$", "test failed"
)


def emit(  # noqa: PLR0913 — one parameter per envelope field
    gate: str,
    *,
    trees: list[str],
    exit_code: int,
    summary: str,
    failures: list[Failure] | None = None,
    issue: int | None = None,
    extra: dict[str, Any] | None = None,
) -> int:
    try:
        head = git("rev-parse", "--short", "HEAD")
    except RuntimeError:
        head = None
    envelope = {
        "gate": gate,
        "trees": trees,
        "exit": exit_code,
        "summary": summary,
        "failures": [f.to_dict() for f in failures or []],
        "extra": {"head": head, **(extra or {})},
    }
    text = json.dumps(envelope, indent=2)
    print(text)
    if issue is not None:
        out = REPO_ROOT / ".reviews" / str(issue) / "gates" / f"{gate}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return exit_code


def run_checks(gate: str, checks: list[Check], args: argparse.Namespace) -> int:
    """Run each check; a non-zero exit with no parsed failures is a harness error (exit 2)."""
    selected = [c for c in checks if c.tree in args.tree]
    failures: list[Failure] = []
    parts: list[str] = []
    errors: list[str] = []
    for check in selected:
        code, out = run(check.cmd, check.cwd)
        found = check.parse(out) if code != 0 else []
        prefix = check.cwd.relative_to(REPO_ROOT)
        for f in found:
            f.extra.setdefault("tool", check.label)
            path = Path(f.file)
            if not path.is_absolute():
                path = prefix / path
            elif path.is_relative_to(REPO_ROOT):
                path = path.relative_to(REPO_ROOT)
            f.file = path.as_posix()
        failures.extend(found)
        if code == 0:
            parts.append(f"{check.label}: ok")
        elif found:
            parts.append(f"{check.label}: {len(found)} failure(s)")
        else:
            errors.append(f"{check.label} exited {code} with unparsed output:\n{tail(out)}")
            parts.append(f"{check.label}: harness error")
    exit_code = 2 if errors else (1 if failures else 0)
    extra = {"errors": errors} if errors else None
    return emit(
        gate,
        trees=args.tree,
        exit_code=exit_code,
        summary=" · ".join(parts),
        failures=failures,
        issue=args.issue,
        extra=extra,
    )
