"""Pins the gate envelope and the per-tool output parsers (scripts/gates/)."""

import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "gates"))
harness = importlib.import_module("_harness")
run_lint = importlib.import_module("run_lint")
run_typecheck = importlib.import_module("run_typecheck")
coverage_delta = importlib.import_module("coverage_delta")

# Captured from ruff 0.17 with colour forced on: SGR codes plus an OSC-8 hyperlink on the rule.
RUFF_CHECK_COLOURED = (
    "\x1b[1mbackend\\zz_lint.py\x1b[0m\x1b[36m:\x1b[0m1\x1b[36m:\x1b[0m8\x1b[36m:\x1b[0m "
    "\x1b[1m\x1b[31m\x1b]8;;https://docs.astral.sh/ruff/rules/unused-import\x1b\\F401"
    "\x1b]8;;\x1b\\\x1b[0m [\x1b[36m*\x1b[0m] `os` imported but unused\n"
    "Found 1 error.\n"
)
RUFF_CHECK_PLAIN = "backend\\zz_lint.py:1:8: F401 [*] `os` imported but unused\nFound 1 error.\n"
RUFF_FORMAT = (
    "backend\\zz_fmt.py:1:2: unformatted: File would be reformatted\n"
    "1 file would be reformatted, 50 files already formatted\n"
)
PYTEST = (
    "FAILED tests/test_x.py::test_breaks - AssertionError: assert 1 == 2\n"
    "ERROR tests/test_y.py\n1 failed, 1 error in 0.1s\n"
)


def check(label: str, checks: list[Any]) -> Any:
    return next(c for c in checks if c.label == label)


def test_ruff_check_output_parses_after_stripping_colour_and_hyperlinks() -> None:
    parse = check("ruff check", run_lint.CHECKS).parse

    for raw in (RUFF_CHECK_COLOURED, RUFF_CHECK_PLAIN):
        [failure] = parse(harness.ANSI.sub("", raw))
        assert failure.to_dict() == {
            "file": "backend/zz_lint.py",
            "line": 1,
            "message": "`os` imported but unused",
            "rule": "F401",
        }


def test_tool_env_never_forces_colour_and_runs_in_mock_mode() -> None:
    assert "FORCE_COLOR" not in harness.TOOL_ENV
    assert harness.TOOL_ENV["NO_COLOR"] == "1"
    assert harness.TOOL_ENV["MOCK_LLM"] == "true"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not on PATH")
def test_real_ruff_lint_error_is_a_failure_even_with_force_color_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    (tmp_path / "bad.py").write_text("import os\n", encoding="utf-8")
    cmd = ["ruff", "check", "--isolated", "--select", "F401", "--output-format", "concise", "."]

    code, out = harness.run(cmd, tmp_path)

    assert code == 1
    [failure] = check("ruff check", run_lint.CHECKS).parse(out)
    assert (failure.file, failure.line, failure.extra["rule"]) == ("bad.py", 1, "F401")


def test_ruff_format_output_parses() -> None:
    [failure] = check("ruff format", run_lint.CHECKS).parse(RUFF_FORMAT)

    assert failure.to_dict() == {
        "file": "backend/zz_fmt.py",
        "line": 1,
        "message": "File would be reformatted",
    }


def test_basedpyright_json_keeps_errors_only() -> None:
    report = {
        "generalDiagnostics": [
            {
                "file": "backend/x.py",
                "severity": "error",
                "message": 'Type "Literal[\'s\']" is not assignable to return type "int"',
                "range": {"start": {"line": 1, "character": 11}},
                "rule": "reportReturnType",
            },
            {
                "file": "backend/x.py",
                "severity": "warning",
                "message": "unused",
                "range": {"start": {"line": 4, "character": 0}},
            },
        ]
    }

    [failure] = run_typecheck.parse_basedpyright(json.dumps(report))

    assert (failure.file, failure.line, failure.extra) == (
        "backend/x.py",
        2,
        {"rule": "reportReturnType"},
    )
    assert run_typecheck.parse_basedpyright("not json") == []


def test_pytest_summary_lines_parse() -> None:
    failed, errored = harness.parse_pytest(PYTEST)

    assert failed.to_dict() == {
        "file": "tests/test_x.py",
        "line": 0,
        "message": "AssertionError: assert 1 == 2",
        "test": "test_breaks",
    }
    assert (errored.file, errored.message) == ("tests/test_y.py", "test failed")


@pytest.mark.parametrize(
    "case",
    [(0, "", 0), (1, RUFF_CHECK_PLAIN, 1), (1, "something unexpected", 2)],
    ids=["pass", "failure", "unparsed-output"],
)
def test_run_checks_envelope_and_exit_codes(
    case: tuple[int, str, int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, expected_exit = case
    monkeypatch.setattr(harness, "run", lambda *_args, **_kw: (code, out))
    monkeypatch.setattr(harness, "git", lambda *_args: "abc1234")
    monkeypatch.setattr(harness, "REPO_ROOT", tmp_path)
    ruff_check = harness.Check(
        "backend", "ruff check", [], check("ruff check", run_lint.CHECKS).parse
    )
    ruff_check.cwd = tmp_path
    args = harness.parse_args(["--tree", "backend", "--issue", "7"])

    result = harness.run_checks("run-lint", [ruff_check], args)

    envelope = json.loads(capsys.readouterr().out)
    assert result == envelope["exit"] == expected_exit
    assert set(envelope) == {"gate", "trees", "exit", "summary", "failures", "extra"}
    assert envelope["gate"] == "run-lint"
    assert envelope["trees"] == ["backend"]
    assert envelope["extra"]["head"] == "abc1234"
    assert len(envelope["failures"]) == (1 if expected_exit == 1 else 0)
    cached = tmp_path / ".reviews" / "7" / "gates" / "run-lint.json"
    assert json.loads(cached.read_text(encoding="utf-8")) == envelope


def test_coverage_threshold_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATE_COVERAGE_MIN", "70%")
    assert coverage_delta.threshold() == pytest.approx(0.7)

    monkeypatch.setenv("GATE_COVERAGE_MIN", "abc")
    with pytest.raises(coverage_delta.GateError) as err:
        coverage_delta.threshold()
    assert err.value.code == 2


def test_coverage_check_file_reports_uncovered_ranges() -> None:
    data = {"executed_lines": [1, 2, 3], "missing_lines": [6, 7, 9]}

    failure = coverage_delta.check_file("backend/x.py", {2, 3, 4, 6, 7, 9}, data, 0.8)

    assert failure is not None
    assert failure.line == 6
    assert failure.extra["coverage_pct"] == 0.4
    assert failure.extra["uncovered_ranges"] == [[6, 7], [9, 9]]
    assert failure.extra["tool"] == "coverage"
    assert coverage_delta.check_file("backend/x.py", {2, 3}, data, 0.8) is None
