"""In-process rate limits for the interview, the hosted demo's only LLM caller (ADR-0011).

Exact only with one instance: the hosted service runs with at most one (ADR-0011 amendment).
"""

import time
from collections import deque
from collections.abc import Callable, Sequence
from typing import Literal

HOUR = 3_600
DAY = 86_400


class RateLimiter:
    """A sliding hour per client address and a global count per UTC day. Only allowed
    messages count, so a refused one never uses up the budget or adds an address."""

    def __init__(self, *, per_ip: int, daily: int, clock: Callable[[], float] = time.time) -> None:
        self.per_ip, self.daily, self.clock = per_ip, daily, clock
        self._recent: dict[str, deque[float]] = {}
        self._day, self._today = -1, 0

    def allow(self, address: str) -> Literal["ip", "daily"] | None:
        """None when the message may go ahead (and is counted), else the limit it hit."""
        now = self.clock()
        if (day := int(now // DAY)) != self._day:
            self._day, self._today = day, 0
        self._forget_quiet(now)
        recent = self._recent.get(address, deque())
        if len(recent) >= self.per_ip:
            return "ip"
        if self._today >= self.daily:
            return "daily"
        recent.append(now)
        self._recent[address] = recent
        self._today += 1
        return None

    def _forget_quiet(self, now: float) -> None:
        """Drop timestamps older than an hour, and addresses left with none."""
        for address in list(self._recent):
            recent = self._recent[address]
            while recent and recent[0] <= now - HOUR:
                recent.popleft()
            if not recent:
                del self._recent[address]


def client_address(forwarded_for: Sequence[str], peer: str | None) -> str:
    """The rightmost X-Forwarded-For entry across every header line. On direct Cloud Run
    (run.app) ingress, Google's front end appends the caller's address, so a client cannot
    forge it. Behind an external HTTPS load balancer the rightmost entry is the balancer's and
    the caller is second from the right: change this before adding one (ADR-0011). Spoofing
    only dodges the per-address limit, never the daily one."""
    entries = [e.strip() for line in forwarded_for for e in line.split(",") if e.strip()]
    return entries[-1] if entries else peer or "unknown"
