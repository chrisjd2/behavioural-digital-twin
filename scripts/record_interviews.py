"""Record 2-3 interview exchanges for the Step 5 fallback (ADR-0008) into the config.

Asks one agent the questions in turn, as one conversation, through the same prompt and the
run's own model as the live interview, then writes `config/interview_recorded.json`. Run it
with the real key (MOCK_LLM=false) against the run the demo ships, usually the frozen one.
Mock mode is refused unless --out names a scratch file, so fake answers never replace the
recording. Any headline the model quotes word for word is replaced by its [id]; if a run of
six or more words from a headline is still there (paraphrased quotes, changed case or quotes),
nothing is written, so the repo holds no MIND text (ADR-0010). Read the answers before
committing.

    uv run python -m scripts.record_interviews --run <run_id> --user <user_id> [--arm D]
    uv run python -m scripts.record_interviews --run <run_id> --user <user_id> \
        --question "What news do you read?" --question "How old are you?"
"""

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path

from backend.config import Settings, get_settings
from backend.errors import AppError
from backend.interview import Interviewer, InterviewRequest, RecordingConfig, agent_result
from backend.run_views import open_run, run_news

DEFAULT_QUESTIONS = [
    "What kind of news do you usually read?",
    "Which of your past clicks says the most about you?",
    "How old are you?",
]
QUOTE_WORDS = 6  # this many words in a row from a headline count as a quote
MIN_QUOTE_WORDS = 4  # shorter headlines are common phrases, not quotes


def without_headlines(text: str, titles: Mapping[str, str]) -> str:
    """Quoted headlines become their [id]; longest first, so a title inside another stays."""
    for news_id, title in sorted(titles.items(), key=lambda t: -len(t[1])):
        text = text.replace(title, f"[{news_id}]")
    return text


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w]+", " ", text.casefold().replace("\u2019", "'")).split()


def quoted_headline(text: str, titles: Mapping[str, str]) -> str | None:
    """The id of a headline still quoted in `text`, ignoring case, quotes and punctuation."""
    said = f" {' '.join(_words(text))} "
    for news_id, title in titles.items():
        words = _words(title)
        n = min(QUOTE_WORDS, len(words))  # a short headline counts whole, if 4+ words
        if n < MIN_QUOTE_WORDS:
            continue
        for start in range(len(words) - n + 1):
            if f" {' '.join(words[start : start + n])} " in said:
                return news_id
    return None


async def record(
    settings: Settings, run_id: str, user_id: str, arm: str, questions: list[str]
) -> RecordingConfig:
    run = open_run(settings, run_id)
    news = run_news(settings, run)
    result = agent_result(run, user_id, arm)
    # Everything the agent saw or was asked about: its history, its candidates, its knowledge.
    seen = {*result.history, *result.items, *re.findall(r"N\d+", json.dumps(result.knowledge))}
    titles = {i: news[i].title for i in seen if i in news and news[i].title}
    interviewer = Interviewer(settings)
    session_id: str | None = None
    exchanges: list[dict[str, str]] = []
    model = "mock"
    for question in questions:
        request = InterviewRequest(
            run_id=run_id, user_id=user_id, arm=arm, session_id=session_id, question=question
        )
        reply = await interviewer.ask(request)
        session_id, model = reply.session_id, reply.model
        answer = without_headlines(reply.text, titles)
        if (news_id := quoted_headline(answer, titles)) is not None:
            raise AppError(
                422,
                "headline_in_answer",
                f"An answer still quotes headline {news_id}; ask again or edit it by hand.",
            )
        exchanges.append({"question": question, "answer": answer})
    return RecordingConfig.model_validate(
        {
            "run_id": run_id,
            "user_id": user_id,
            "arm": arm,
            "model": model,
            "mock": model == "mock",
            "exchanges": exchanges,
        }
    )


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record interview exchanges for the Step 5 fallback."
    )
    parser.add_argument("--run", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--arm", default="D", choices=["A", "B", "C", "D", "E"])
    parser.add_argument("--question", action="append", help="repeat; default: three starters")
    parser.add_argument("--out", help="default: INTERVIEW_RECORDED (refused in mock mode)")
    args = parser.parse_args(argv)
    settings = settings or get_settings()
    if settings.mock_llm and not args.out:
        print("MOCK_LLM is on: refusing to overwrite the recording with fake answers.")
        print("Set MOCK_LLM=false with a key, or pass --out for a scratch file.")
        return 1
    if not settings.mock_llm and not settings.llm_api_key:
        print("No LLM_API_KEY: set it in .env to record real answers.")
        return 1
    questions = args.question or DEFAULT_QUESTIONS
    try:
        recording = asyncio.run(record(settings, args.run, args.user, args.arm, questions))
    except AppError as exc:
        print(exc.detail, file=sys.stderr)
        return 1
    out = Path(args.out or settings.interview_recorded)
    out.write_text(json.dumps(recording.model_dump(), indent=2) + "\n", encoding="utf-8")
    if recording.mock:
        print("Mock run or MOCK_LLM: these are fake, MOCK-labelled answers.", file=sys.stderr)
    for e in recording.exchanges:
        print(f"Q: {e.question}\nA: {e.answer}\n")
    print(f"Wrote {len(recording.exchanges)} exchanges to {out}. Read them before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
