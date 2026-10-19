"""scripts.record_interviews: the recorded fallback is made the way the live interview is."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from backend import interview
from backend.interview import read_recording
from backend.llm import RawResponse
from backend.runner import Run
from scripts.record_interviews import DEFAULT_QUESTIONS, main, quoted_headline
from tests.test_interview import knowledge, make_lab
from tests.test_status import make_settings


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Run]:
    return make_lab(tmp_path_factory)


def run_script(lab: tuple[Path, Run], out: Path, *args: str) -> int:
    run = lab[1]
    settings = make_settings(data_dir=str(lab[0]))
    argv = ["--run", run.run_id, "--user", run.users[0].user_id, "--out", str(out), *args]
    return main(argv, settings)


def test_records_the_default_questions_as_one_conversation(
    lab: tuple[Path, Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []
    original = interview.mock_interview_backend

    async def spy(payload: Mapping[str, object]) -> RawResponse:
        messages = payload["messages"]
        assert isinstance(messages, list)
        seen.append(len(messages))
        return await original(payload)

    monkeypatch.setattr(interview, "mock_interview_backend", spy)
    out = tmp_path / "recorded.json"

    assert run_script(lab, out) == 0

    recording = read_recording(out)
    assert [e.question for e in recording.exchanges] == list(DEFAULT_QUESTIONS)
    assert recording.mock is True
    assert recording.arm == "D"
    assert seen == [2, 4, 6]  # system + each earlier turn


def test_quoted_headlines_are_replaced_by_their_ids(
    lab: tuple[Path, Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = knowledge(lab[1], "D")["memories"][0]  # pyright: ignore[reportIndexIssue]

    async def quoting(_: Mapping[str, object]) -> RawResponse:
        return RawResponse(f'I clicked "{memory["headline"]}".', 0, 0)

    monkeypatch.setattr(interview, "mock_interview_backend", quoting)
    out = tmp_path / "recorded.json"

    assert run_script(lab, out, "--question", "What do you read?") == 0

    answer = json.loads(out.read_text(encoding="utf-8"))["exchanges"][0]["answer"]
    assert answer == f'I clicked "[{memory["news_id"]}]".'


def test_a_reworded_quote_is_refused_and_nothing_is_written(
    lab: tuple[Path, Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = knowledge(lab[1], "D")["memories"][0]  # pyright: ignore[reportIndexIssue]
    reworded = str(memory["headline"]).upper().replace("[", "(").replace("]", ")")

    async def quoting(_: Mapping[str, object]) -> RawResponse:
        return RawResponse(f"I liked \u2018{reworded}\u2019!", 0, 0)

    monkeypatch.setattr(interview, "mock_interview_backend", quoting)
    out = tmp_path / "recorded.json"

    assert run_script(lab, out, "--question", "What do you read?") == 1
    assert not out.exists()


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("I read “the quick brown fox jumps over” daily", "N1"),
        ("I read about foxes and dogs", None),
        ("Short Title Here", None),  # under four words is a phrase, not a quote
    ],
)
def test_quoted_headline_ignores_case_and_quotes(text: str, found: str | None) -> None:
    titles = {"N1": "The Quick Brown Fox Jumps Over the Lazy Dog", "N2": "Short Title Here"}

    assert quoted_headline(text, titles) == found


def test_mock_mode_never_overwrites_the_recording(
    lab: tuple[Path, Run], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recording = tmp_path / "interview_recorded.json"
    settings = make_settings(data_dir=str(lab[0]), interview_recorded=str(recording))

    code = main(["--run", lab[1].run_id, "--user", lab[1].users[0].user_id], settings)

    assert code == 1
    assert not recording.exists()
    assert "refusing to overwrite" in capsys.readouterr().out


def test_no_key_is_a_clean_error(
    lab: tuple[Path, Run], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "recorded.json"
    settings = make_settings(data_dir=str(lab[0]), mock_llm=False, llm_api_key="")

    code = main(["--run", lab[1].run_id, "--user", "U1", "--out", str(out)], settings)

    assert code == 1
    assert not out.exists()
    assert "No LLM_API_KEY" in capsys.readouterr().out


def test_an_unknown_reader_is_reported_and_nothing_is_written(
    lab: tuple[Path, Run], tmp_path: Path
) -> None:
    out = tmp_path / "recorded.json"
    settings = make_settings(data_dir=str(lab[0]))

    code = main(["--run", lab[1].run_id, "--user", "U-nobody", "--out", str(out)], settings)

    assert code == 1
    assert not out.exists()
