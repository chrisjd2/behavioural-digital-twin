"""Step 5 Interview: chat with one agent in one arm under the trust guardrails (ADR-0007).

The agent knows only what it knew in the run (the run file's `knowledge`), never the
headlines it was predicting or their labels. The interview is the hosted demo's only LLM
caller, so it is rate-limited in-process (ADR-0011); past the limits, or when the live call
fails, the UI shows the recorded exchanges from `config/interview_recorded.json` (ADR-0008).
"""

import asyncio
import hashlib
import json
import re
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Literal, Self

import openai
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.config import Settings
from backend.errors import AppError
from backend.llm import Cache, LLMClient, RawResponse, TransientError, openai_backend
from backend.profiles import PROFILE_FIELDS
from backend.run_views import Headline, by_user, headlines, open_run, run_news
from backend.runner import LLM_ARMS, Run, UserResult

MAX_TURNS = 20  # the UI sends only the latest turns
MAX_QUESTION_CHARS = 1000
MAX_ANSWER_CHARS = 20_000  # the agent's own replies, sent back as context; not capped live

REFUSAL = "I don't know, it's not in my data."

# ADR-0007's interview rules, near verbatim; every arm gets them.
SCOPE_RULE = (
    "Talk only about news interests and reading habits; cite past clicks where you can, by "
    "their id in square brackets, like [N12345]."
)
IDENTITY_RULE = (
    "If asked about identity, demographics, beliefs or anything not in the evidence below, "
    f'say you don\'t know because it is not in the data: "{REFUSAL}"'
)
STYLE_RULE = "Never claim to be a real person. Answer in the first person, in 2-4 sentences."

TWIN_INTRO = "You are a simulation built only from this person's news-click history."

ARM_INTROS = {
    "A": (
        "You are a simulation of a typical Microsoft News reader. You know nothing about any "
        "particular reader: no clicks and no profile, so you can only speak in general terms."
    ),
    "B": (
        "You are an invented character, not a real person and not built from anyone's data. "
        "Say openly that you are invented whenever you describe yourself. The invented details "
        "below shape only your news habits; they are not evidence about any reader, so the "
        "identity rule applies to them too."
    ),
    "C": TWIN_INTRO,
    "D": TWIN_INTRO,
    "E": (
        "You are a control simulation, the wrong twin: you are built from another reader's "
        "news-click history, not the history of the person you are asked about. Say openly "
        "that your clicks and profile are another reader's data."
    ),
}

_CITATION = re.compile(r"\[([^\]]+)\]")
_ID = re.compile(r"N\d+")
_IDENTITY_QUESTION = re.compile(
    r"\b(how old|your age|gender|married|vote|religio|where do you live|your job|income)",
    re.IGNORECASE,
)
_MEMORY_LINE = re.compile(r"^- \[(N\d+)\]", re.MULTILINE)


def _persona_block(persona: Mapping[str, object]) -> str:
    big_five, values = persona["big_five"], persona["values"]
    assert isinstance(big_five, dict)
    assert isinstance(values, list)
    traits = ", ".join(f"{level} {trait}" for trait, level in big_five.items())
    return (
        f"The invented character: {persona['name']}, {persona['age']}, {persona['job']} in "
        f"{persona['location']}. Personality: {traits}. Values: {' and '.join(values)}. "
        f"{persona['news_habit']}"
    )


def _profile_block(profile: Mapping[str, object]) -> str:
    """The profile's text with its evidence ids, so the agent can cite them. An unusable
    profile was never shown to the agent (ADR-0007), so it is not shown here either."""
    fields = profile["fields"]
    assert isinstance(fields, dict)
    lines = []
    for name in PROFILE_FIELDS:
        for item in fields.get(name, []):
            evidence = "".join(f"[{e}]" for e in item["evidence"])
            lines.append(f"- {name.replace('_', ' ')}: {item['text']} {evidence}")
    return "\n".join(lines)


def _memories_block(memories: Sequence[Mapping[str, object]]) -> str:
    # Not the retrieval reason: "similar to: ..." quotes a headline being predicted.
    return "\n".join(f"- [{m['news_id']}] ({m['category']}) {m['headline']}" for m in memories)


def interview_system_prompt(arm: str, knowledge: Mapping[str, object]) -> str:
    """ADR-0007's interview prompt over what this agent knew in the run, and nothing else."""
    parts = [ARM_INTROS[arm], SCOPE_RULE, IDENTITY_RULE, STYLE_RULE]
    owner = "Another reader's" if arm == "E" else "Your"
    if arm == "B":
        parts.append(_persona_block(knowledge))
    if isinstance(profile := knowledge.get("profile"), dict) and profile["ok"]:
        parts.append(f"{owner} reading profile, with the clicks behind each point:\n")
        parts[-1] += _profile_block(profile)
    if isinstance(memories := knowledge.get("memories"), list):
        parts.append(f"{owner} past clicks:\n{_memories_block(memories)}")
    return "\n\n".join(parts)


def known_ids(knowledge: Mapping[str, object]) -> set[str]:
    """The past clicks an agent may cite: its memories and its profile's evidence."""
    ids: set[str] = set()
    if isinstance(memories := knowledge.get("memories"), list):
        ids.update(str(m["news_id"]) for m in memories)
    if isinstance(profile := knowledge.get("profile"), dict) and profile["ok"]:
        for items in profile["fields"].values():
            ids.update(e for item in items for e in item["evidence"])
    return ids


def cited_ids(text: str, knowledge: Mapping[str, object]) -> list[str]:
    """Bracketed ids the agent really knew, in order of first citation; others are ignored."""
    known = known_ids(knowledge)
    found = (i for group in _CITATION.findall(text) for i in _ID.findall(group))
    return [i for i in dict.fromkeys(found) if i in known]


class Turn(BaseModel):
    role: Literal["interviewer", "agent"]
    text: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)

    @model_validator(mode="after")
    def _short_question(self) -> Self:
        if self.role == "interviewer" and len(self.text) > MAX_QUESTION_CHARS:
            raise ValueError(f"A question may be at most {MAX_QUESTION_CHARS} characters.")
        return self


class InterviewRequest(BaseModel):
    run_id: str
    user_id: str
    arm: str
    messages: list[Turn] = Field(min_length=1, max_length=MAX_TURNS)  # oldest first


class InterviewReply(BaseModel):
    run_id: str
    user_id: str
    arm: str
    text: str
    mock: bool  # a fake reply from the mock LLM: never a result
    cited: list[Headline]  # past clicks the reply cites, in order


class RecordedExchange(BaseModel):
    question: str
    answer: str
    cited: list[Headline]


class RecordedInterview(BaseModel):
    """Shown, labelled "recorded", when the live interview fails or is rate-limited."""

    run_id: str
    user_id: str
    arm: str
    model: str
    mock: bool
    exchanges: list[RecordedExchange]


class _StoredExchange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str


class RecordingConfig(BaseModel):
    """`config/interview_recorded.json`: ids and generated text only, no MIND headlines."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    user_id: str
    arm: str
    model: str
    mock: bool
    exchanges: list[_StoredExchange] = Field(min_length=1)


class RateLimiter:
    """ADR-0011: a sliding hour per client address and a global count per UTC day. Only
    allowed messages count, so a refused one never uses up the budget."""

    def __init__(self, *, per_ip: int, daily: int, clock: Callable[[], float] = time.time) -> None:
        self.per_ip, self.daily, self.clock = per_ip, daily, clock
        self._recent: dict[str, deque[float]] = {}
        self._day, self._today = -1, 0

    def allow(self, address: str) -> Literal["ip", "daily"] | None:
        """None when the message may go ahead (and is counted), else the limit it hit."""
        now = self.clock()
        if (day := int(now // 86_400)) != self._day:
            self._day, self._today = day, 0
            # Forget addresses with nothing in the last hour, so memory stays bounded.
            self._recent = {a: q for a, q in self._recent.items() if q and q[-1] > now - 3_600}
        recent = self._recent.setdefault(address, deque())
        while recent and recent[0] <= now - 3_600:
            recent.popleft()
        if len(recent) >= self.per_ip:
            return "ip"
        if self._today >= self.daily:
            return "daily"
        recent.append(now)
        self._today += 1
        return None


def client_address(forwarded_for: str | None, peer: str | None) -> str:
    """Cloud Run appends the caller's address to X-Forwarded-For, so the last hop is the one
    a client cannot forge. Spoofing elsewhere only dodges the per-address limit, never the
    daily one."""
    if forwarded_for and (last := forwarded_for.split(",")[-1].strip()):
        return last
    return peer or "unknown"


async def mock_interview_backend(payload: Mapping[str, object]) -> RawResponse:
    """A deterministic fake reply, labelled MOCK, citing the agent's first two memories. An
    identity question gets the refusal the prompt asks for, so the UI path can be seen without
    a key; the real guardrail is the system prompt, not this."""
    messages = payload["messages"]
    assert isinstance(messages, list)
    if _IDENTITY_QUESTION.search(str(messages[-1]["content"])):
        return RawResponse(f"MOCK reply. {REFUSAL}", prompt_tokens=0, completion_tokens=0)
    ids = _MEMORY_LINE.findall(str(messages[0]["content"]))[:2]
    clicks = f"I would cite {' and '.join(f'[{i}]' for i in ids)}." if ids else "No clicks."
    digest = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:6]
    return RawResponse(f"MOCK reply {digest}. {clicks}", prompt_tokens=0, completion_tokens=0)


retry_sleep = asyncio.sleep


class NoCache(Cache):
    """The interview is a conversation, not an experiment: replies are never cached, so it
    writes nothing to DATA_DIR and keeps ADR-0002's one cache for runs."""

    def __init__(self) -> None:  # pyright: ignore[reportMissingSuperCall] -- no SQLite file
        pass

    def get(self, key: str) -> str | None:
        return None

    def put(self, key: str, model: str, content: str) -> None:
        pass


def interview_client(settings: Settings) -> LLMClient:
    """The configured model and endpoint: the frozen run's, in the hosted demo."""
    if settings.mock_llm:
        backend, model, base_url = mock_interview_backend, "mock", "mock://"
    else:
        backend = openai_backend(settings.llm_base_url, settings.llm_api_key)
        model, base_url = settings.llm_model, settings.llm_base_url
    return LLMClient(
        model=model,
        base_url=base_url,
        cache=NoCache(),
        backend=backend,
        concurrency=settings.concurrency,
        sleep=retry_sleep,
    )


def agent_result(run: Run, user_id: str, arm: str) -> UserResult:
    results = by_user(run).get(user_id)
    if results is None:
        raise AppError(404, "agent_not_found", f"User {user_id} is not in run {run.run_id}.")
    found = next((r for r in results if r.arm == arm and arm in LLM_ARMS), None)
    if found is None:
        raise AppError(404, "arm_not_in_run", f"Arm {arm} is not an LLM arm of run {run.run_id}.")
    return found


def interview_payload(
    system: str, messages: Sequence[Turn], settings: Settings
) -> dict[str, object]:
    roles = {"interviewer": "user", "agent": "assistant"}
    return {
        "messages": [
            {"role": "system", "content": system},
            *({"role": roles[t.role], "content": t.text} for t in messages),
        ],
        "temperature": 0,
        "reasoning_effort": settings.llm_reasoning_effort,
        "max_tokens": settings.llm_max_output_tokens,
    }


async def ask_agent(
    settings: Settings, client: LLMClient, request: InterviewRequest
) -> InterviewReply:
    if request.messages[-1].role != "interviewer":
        raise AppError(422, "no_question", "The last message must be the interviewer's question.")
    run = open_run(settings, request.run_id)
    result = agent_result(run, request.user_id, request.arm)
    payload = interview_payload(
        interview_system_prompt(request.arm, result.knowledge), request.messages, settings
    )
    try:
        text = (await client.complete(payload)).content.strip()
    except (TransientError, openai.OpenAIError) as exc:
        raise AppError(502, "interview_unavailable", f"The live interview failed: {exc}") from exc
    if not text:
        raise AppError(502, "interview_unavailable", "The live interview returned no reply.")
    return InterviewReply(
        run_id=run.run_id,
        user_id=request.user_id,
        arm=request.arm,
        text=text,
        mock=settings.mock_llm,
        cited=headlines(cited_ids(text, result.knowledge), run_news(settings, run)),
    )


def read_recording(path: Path) -> RecordingConfig:
    if not path.is_file():
        raise AppError(
            404,
            "interview_not_recorded",
            f"No recorded interview: {path} is missing. Record one with scripts.record_interviews.",
        )
    try:
        return RecordingConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise AppError(
            422, "interview_recording_invalid", f"{path} is not a recorded interview: {exc}"
        ) from exc


def recorded_interview(settings: Settings, recording: RecordingConfig) -> RecordedInterview:
    run = open_run(settings, recording.run_id)
    knowledge = agent_result(run, recording.user_id, recording.arm).knowledge
    news = run_news(settings, run)
    return RecordedInterview(
        run_id=recording.run_id,
        user_id=recording.user_id,
        arm=recording.arm,
        model=recording.model,
        mock=recording.mock,
        exchanges=[
            RecordedExchange(
                question=e.question,
                answer=e.answer,
                cited=headlines(cited_ids(e.answer, knowledge), news),
            )
            for e in recording.exchanges
        ],
    )


LIMIT_DETAILS = {
    "ip": "Interview limit reached: {n} messages an hour from one address.",
    "daily": "Interview limit reached: {n} messages a day for everyone.",
}


def interview_router(settings: Settings) -> APIRouter:
    """The same in `DEMO_MODE`: the interview is the demo's one allowed LLM caller, and the
    rate limits apply in every mode so local and hosted behave alike (ADR-0011)."""
    router = APIRouter()

    @cache
    def client() -> LLMClient:
        """Built on first use: without a key the app still starts, and only this fails."""
        try:
            return interview_client(settings)
        except openai.OpenAIError as exc:
            raise AppError(502, "interview_unavailable", f"No live LLM: {exc}") from exc

    limiter = RateLimiter(
        per_ip=settings.interview_ip_limit_per_hour, daily=settings.interview_daily_limit
    )

    @router.post("/api/interview")
    async def interview(request: InterviewRequest, http: Request) -> InterviewReply:  # pyright: ignore[reportUnusedFunction]
        address = client_address(
            http.headers.get("x-forwarded-for"), http.client.host if http.client else None
        )
        if limit := limiter.allow(address):
            n = limiter.per_ip if limit == "ip" else limiter.daily
            raise AppError(429, "rate_limited", LIMIT_DETAILS[limit].format(n=n))
        return await ask_agent(settings, client(), request)

    @router.get("/api/interview/recorded")
    def recorded() -> RecordedInterview:  # pyright: ignore[reportUnusedFunction]
        return recorded_interview(settings, read_recording(Path(settings.interview_recorded)))

    return router
