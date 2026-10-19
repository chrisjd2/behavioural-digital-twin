"""backend.rate_limit: the interview's limits (ADR-0011), with a fake clock."""

from backend.config import Settings
from backend.rate_limit import RateLimiter, client_address


class FakeClock:
    def __init__(self, at: float = 1_000_000.0) -> None:
        self.at = at

    def __call__(self) -> float:
        return self.at


def test_per_ip_limit_is_a_sliding_hour() -> None:
    start = 1_000_000.0
    clock = FakeClock(start)
    limiter = RateLimiter(per_ip=30, daily=500, clock=clock)

    for _ in range(30):
        assert limiter.allow("1.1.1.1") is None
        clock.at += 60
    assert limiter.allow("1.1.1.1") == "ip"
    assert limiter.allow("2.2.2.2") is None  # another address is unaffected
    clock.at = start + 3_599  # the first message is not yet an hour old
    assert limiter.allow("1.1.1.1") == "ip"
    clock.at = start + 3_600
    assert limiter.allow("1.1.1.1") is None
    assert limiter.allow("1.1.1.1") == "ip"  # only the oldest message has expired


def test_daily_limit_is_global_and_resets_at_midnight_utc() -> None:
    clock = FakeClock(at=86_400 * 20_000 + 3_600)
    limiter = RateLimiter(per_ip=30, daily=500, clock=clock)

    for n in range(500):
        assert limiter.allow(f"10.0.{n // 250}.{n % 250}") is None
    assert limiter.allow("9.9.9.9") == "daily"
    clock.at = 86_400 * 20_001  # the next UTC day
    assert limiter.allow("9.9.9.9") is None


def test_refused_messages_do_not_count_or_add_addresses() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_ip=1, daily=2, clock=clock)

    assert limiter.allow("a") is None
    assert limiter.allow("a") == "ip"
    assert limiter.allow("b") is None  # the refused message did not use the daily budget
    assert limiter.allow("c") == "daily"
    assert set(limiter._recent) == {"a", "b"}  # pyright: ignore[reportPrivateUsage]


def test_addresses_quiet_for_an_hour_are_forgotten() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_ip=30, daily=500, clock=clock)
    limiter.allow("old")
    clock.at += 3_600

    limiter.allow("new")

    assert set(limiter._recent) == {"new"}  # pyright: ignore[reportPrivateUsage]


def test_client_address_is_the_rightmost_forwarded_entry_across_header_lines() -> None:
    assert client_address(["spoofed, 203.0.113.9"], "10.0.0.1") == "203.0.113.9"
    assert client_address(["1.1.1.1", "spoofed, 203.0.113.9"], "10.0.0.1") == "203.0.113.9"
    assert client_address([], "10.0.0.1") == "10.0.0.1"
    assert client_address([" , "], None) == "unknown"


def test_default_limits_are_the_adr_ones() -> None:
    settings = Settings()

    assert (settings.interview_ip_limit_per_hour, settings.interview_daily_limit) == (30, 500)
