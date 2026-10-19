"""Record 2-3 interview exchanges for the Step 5 fallback (ADR-0008) into the config.

Asks one agent the questions in turn, as one conversation, through the same prompt and model
as the live interview, then writes `config/interview_recorded.json`. Run it with the real
key (MOCK_LLM=false) against the run the demo ships, usually the frozen one. Any headline the
model quotes word for word is replaced by its [id], so the repo holds no MIND text (ADR-0010);
the app shows the headline from the run's data.

    uv run python -m scripts.record_interviews --run <run_id> --user <user_id> [--arm D]
    uv run python -m scripts.record_interviews --run <run_id> --user <user_id> \
        --question "What news do you read?" --question "How old are you?"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from backend.config import Settings, get_settings
from backend.errors import AppError
from backend.interview import (
    InterviewRequest,
    RecordingConfig,
    Turn,
    agent_result,
    ask_agent,
    interview_client,
    known_ids,
)
from backend.run_views import open_run, run_news

DEFAULT_QUESTIONS = [
    "What kind of news do you usually read?",
    "Which of your past clicks says the most about you?",
    "How old are you?",
]


def without_headlines(text: str, titles: dict[str, str]) -> str:
    """Quoted headlines become their [id]; longest first, so a title inside another stays."""
    for news_id, title in sorted(titles.items(), key=lambda t: -len(t[1])):
        text = text.replace(title, f"[{news_id}]")
    return text


async def record(
    settings: Settings, run_id: str, user_id: str, arm: str, questions: list[str]
) -> RecordingConfig:
    run = open_run(settings, run_id)
    news = run_news(settings, run)
    knowledge = agent_result(run, user_id, arm).knowledge
    titles = {i: news[i].title for i in known_ids(knowledge) if i in news and news[i].title}
    client = interview_client(settings)
    turns: list[Turn] = []
    exchanges: list[dict[str, str]] = []
    for question in questions:
        turns.append(Turn(role="interviewer", text=question))
        request = InterviewRequest(run_id=run_id, user_id=user_id, arm=arm, messages=turns)
        reply = await ask_agent(settings, client, request)
        turns.append(Turn(role="agent", text=reply.text))
        exchanges.append({"question": question, "answer": without_headlines(reply.text, titles)})
    return RecordingConfig.model_validate(
        {
            "run_id": run_id,
            "user_id": user_id,
            "arm": arm,
            "model": client.model,
            "mock": settings.mock_llm,
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
    parser.add_argument("--out", help="default: INTERVIEW_RECORDED")
    args = parser.parse_args(argv)
    settings = settings or get_settings()
    questions = args.question or DEFAULT_QUESTIONS
    try:
        recording = asyncio.run(record(settings, args.run, args.user, args.arm, questions))
    except AppError as exc:
        print(exc.detail, file=sys.stderr)
        return 1
    out = Path(args.out or settings.interview_recorded)
    out.write_text(json.dumps(recording.model_dump(), indent=2) + "\n", encoding="utf-8")
    if recording.mock:
        print("MOCK_LLM is on: these are fake, MOCK-labelled answers.", file=sys.stderr)
    for e in recording.exchanges:
        print(f"Q: {e.question}\nA: {e.answer}\n")
    print(f"Wrote {len(recording.exchanges)} exchanges to {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
