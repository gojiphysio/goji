"""Unit tests for the Plato client's caching + pacing guards (no network).

These cover the two failure modes behind the 2026-09-01 booking outage:
a malformed config response poisoning the 5-minute config cache, and the
un-paced request volume that kept tripping Plato's 20 req/min cap.
"""
from __future__ import annotations

import time

import pytest

from booking.plato import PlatoClient, PlatoError, _RateLimiter


class FakePlato(PlatoClient):
    """PlatoClient with the HTTP layer swapped for a scripted queue of replies.

    Each entry is either a value to return or an Exception to raise.
    """

    def __init__(self, replies):
        super().__init__(db="test", token="test-token")
        self.replies = list(replies)
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, path, params=None, _retries=3):  # noqa: D102 - overrides transport
        self.calls.append((path, params))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


GOOD_CFG = {"calendars": [{"id": "dDIjWJp", "rules": []}]}


def expire_config(p: FakePlato) -> None:
    """Age the config cache past CONFIG_TTL_S.

    Must be relative to `time.monotonic()`, not set to 0.0: monotonic() is
    seconds-since-boot, so on a fresh CI runner it is far below CONFIG_TTL_S
    and a literal 0.0 leaves the entry looking *fresh*. That made these tests
    pass vacuously on the runner while exercising nothing.
    """
    from booking import plato as plato_mod
    p._cfg_ts = time.monotonic() - plato_mod.CONFIG_TTL_S - 1


# --- config cache poisoning -------------------------------------------------

def test_malformed_config_raises_on_cold_cache():
    """A bare list (what Plato returns on some throttled reads) must not be
    handed to the caller as a config — `_rules_for` would die on `.get`."""
    p = FakePlato([[]])
    with pytest.raises(PlatoError, match="malformed booking config"):
        p.online_booking_config()


def test_malformed_config_is_never_cached():
    """The outage's real amplifier: caching the bad response meant every
    availability call failed for CONFIG_TTL_S after Plato had recovered."""
    p = FakePlato([[], GOOD_CFG])
    with pytest.raises(PlatoError):
        p.online_booking_config()
    assert p.online_booking_config() == GOOD_CFG  # recovers on the very next call


def test_malformed_config_falls_back_to_last_good_copy():
    p = FakePlato([GOOD_CFG, []])
    assert p.online_booking_config() == GOOD_CFG
    expire_config(p)
    assert p.online_booking_config() == GOOD_CFG  # stale-but-good beats failing


def test_config_refresh_error_falls_back_to_last_good_copy():
    p = FakePlato([GOOD_CFG, RuntimeError("429 Too Many Requests")])
    assert p.online_booking_config() == GOOD_CFG
    expire_config(p)
    assert p.online_booking_config() == GOOD_CFG


def test_config_refresh_error_propagates_on_cold_cache():
    p = FakePlato([RuntimeError("429 Too Many Requests")])
    with pytest.raises(RuntimeError, match="429"):
        p.online_booking_config()


def test_dict_without_calendars_is_rejected():
    """Plato's error envelopes are dicts too — shape, not just type."""
    p = FakePlato([{"message": "rate limit exceeded"}])
    with pytest.raises(PlatoError, match="malformed booking config"):
        p.online_booking_config()


def test_good_config_is_cached():
    p = FakePlato([GOOD_CFG])
    assert p.online_booking_config() == GOOD_CFG
    assert p.online_booking_config() == GOOD_CFG  # no second fetch; queue is empty


# --- appointment cache TTLs -------------------------------------------------

def test_range_fetches_cache_longer_than_single_days():
    """Month summaries re-page the same range for every focus/clinician
    variant; a 20s TTL made each one a fresh 10+ page crawl."""
    from booking import plato as plato_mod

    p = FakePlato([[], []])
    p.appointments("2026-09-01", "2026-09-30")
    p.appointments("2026-09-01", "2026-09-01")
    # Age both entries past the single-day TTL but not the range TTL.
    aged = time.monotonic() - (plato_mod.APPTS_TTL_S + 5)
    for key in list(p._appts_cache):
        rows = p._appts_cache[key][1]
        p._appts_cache[key] = (aged, rows)

    before = len(p.calls)
    p.appointments("2026-09-01", "2026-09-30")
    assert len(p.calls) == before, "range fetch should still be cached"

    p.replies.append([])
    p.appointments("2026-09-01", "2026-09-01")
    assert len(p.calls) == before + 1, "single-day fetch should have expired"


# --- rate limiter -----------------------------------------------------------

def test_limiter_allows_a_full_burst_immediately():
    lim = _RateLimiter(rate_per_min=60, burst=5)
    started = time.monotonic()
    for _ in range(5):
        lim.acquire(max_wait_s=0.0)
    assert time.monotonic() - started < 0.1


def test_limiter_raises_rather_than_hanging_when_drained():
    """Better to degrade to "no slots" than hold a booking request open."""
    lim = _RateLimiter(rate_per_min=60, burst=1)
    lim.acquire(max_wait_s=0.0)
    with pytest.raises(PlatoError, match="rate budget exhausted"):
        lim.acquire(max_wait_s=0.0)


def test_limiter_refills_over_time():
    lim = _RateLimiter(rate_per_min=6000, burst=1)  # 10ms per token
    lim.acquire(max_wait_s=0.0)
    lim.acquire(max_wait_s=1.0)  # waits ~10ms rather than raising


def test_limiter_disabled_when_rate_is_zero():
    lim = _RateLimiter(rate_per_min=0, burst=1)
    for _ in range(50):
        lim.acquire(max_wait_s=0.0)


def test_stale_config_backs_off_before_retrying_plato():
    """Mid-incident, an expired TTL must not turn every request into another
    failing Plato call — the fallback holds off for CONFIG_RETRY_S."""
    from booking import plato as plato_mod

    p = FakePlato([GOOD_CFG, RuntimeError("429")])
    assert p.online_booking_config() == GOOD_CFG
    expire_config(p)
    assert p.online_booking_config() == GOOD_CFG  # consumes the failing reply

    before = len(p.calls)
    assert p.online_booking_config() == GOOD_CFG  # served from cache, no fetch
    assert len(p.calls) == before

    # ...and it does retry once the back-off window passes.
    p._cfg_ts -= plato_mod.CONFIG_RETRY_S + 1
    p.replies.append(GOOD_CFG)
    assert p.online_booking_config() == GOOD_CFG
    assert len(p.calls) == before + 1
