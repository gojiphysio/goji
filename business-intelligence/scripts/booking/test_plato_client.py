"""Unit tests for the Plato client's caching + pacing guards (no network).

These cover the two failure modes behind the 2026-09-01 booking outage:
a malformed config response poisoning the 5-minute config cache, and the
un-paced request volume that kept tripping Plato's 20 req/min cap.
"""
from __future__ import annotations

import time

import pytest

from booking.plato import PlatoBusy, PlatoClient, PlatoError, PlatoThrottled, _RateLimiter


class FakePlato(PlatoClient):
    """PlatoClient with the HTTP layer swapped for a scripted queue of replies.

    Each entry is either a value to return or an Exception to raise.
    """

    def __init__(self, replies):
        super().__init__(db="test", token="test-token")
        self.replies = list(replies)
        self.calls: list[tuple[str, dict | None]] = []
        self.bulk_flags: list[bool] = []

    def get(self, path, params=None, _retries=3, bulk=False, max_wait_s=None):  # noqa: D102 - overrides transport
        self.calls.append((path, params))
        self.bulk_flags.append(bulk)
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
    aged = time.monotonic() - (max(plato_mod.APPTS_TTL_S,
                                   plato_mod.DAY_FROM_RANGE_MAX_AGE_S) + 5)
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

def test_limiter_allows_a_full_window_immediately():
    lim = _RateLimiter(limit_per_min=5)
    started = time.monotonic()
    for _ in range(5):
        lim.acquire(max_wait_s=0.0)
    assert time.monotonic() - started < 0.1


def test_limiter_never_exceeds_the_cap_in_a_window():
    """The old token bucket (burst 12 + 18/min) let ~30 requests through in the
    first minute against Plato's cap of 20, so a long month fetch drew a 429 on
    itself. The window must hold at most `limit`, full stop."""
    lim = _RateLimiter(limit_per_min=20)
    for _ in range(20):
        lim.acquire(max_wait_s=0.0)
    with pytest.raises(PlatoError, match="budget exhausted"):
        lim.acquire(max_wait_s=0.0)


def test_limiter_raises_rather_than_hanging_when_drained():
    """Better to degrade to "no slots" than hold a booking request open."""
    lim = _RateLimiter(limit_per_min=1)
    lim.acquire(max_wait_s=0.0)
    with pytest.raises(PlatoError, match="budget exhausted"):
        lim.acquire(max_wait_s=0.0)


def test_limiter_frees_a_slot_as_old_requests_leave_the_window():
    lim = _RateLimiter(limit_per_min=2)
    lim.WINDOW_S = 0.2
    lim.acquire(max_wait_s=0.0)
    lim.acquire(max_wait_s=0.0)
    started = time.monotonic()
    lim.acquire(max_wait_s=1.0)  # waits for the first to age out, rather than raising
    assert time.monotonic() - started >= 0.15


def test_bulk_work_cannot_use_the_interactive_reserve():
    """A month crawl may only take `limit - reserve` of the window, so a date
    click or a booking write always finds budget."""
    lim = _RateLimiter(limit_per_min=10, bulk_reserve=4)
    for _ in range(6):
        lim.acquire(max_wait_s=0.0, bulk=True)
    with pytest.raises(PlatoError, match="budget exhausted"):
        lim.acquire(max_wait_s=0.0, bulk=True)
    for _ in range(4):                      # the reserve is still all there
        lim.acquire(max_wait_s=0.0)
    with pytest.raises(PlatoError, match="budget exhausted"):
        lim.acquire(max_wait_s=0.0)


def test_reserve_never_starves_the_limiter_entirely():
    lim = _RateLimiter(limit_per_min=3, bulk_reserve=50)
    lim.acquire(max_wait_s=0.0, bulk=True)  # at least one slot stays bulk-usable


def test_penalise_stops_every_caller_not_just_the_throttled_one():
    """The circuit breaker: retrying into a 429 is what pins the budget, so one
    429 has to stand the whole process down."""
    lim = _RateLimiter(limit_per_min=100)  # plenty of budget
    lim.acquire(max_wait_s=0.0)            # freely available
    lim.penalise(cooldown_s=30)
    with pytest.raises(PlatoError, match="cooling down after a 429"):
        lim.acquire(max_wait_s=0.0)


def test_penalty_expires():
    lim = _RateLimiter(limit_per_min=100)
    lim.penalise(cooldown_s=0.05)
    lim.acquire(max_wait_s=1.0)  # waits out the cooldown instead of raising


def test_penalty_never_shortens_an_existing_cooldown():
    """Concurrent 429s must not let a later, shorter penalty undo a longer one."""
    lim = _RateLimiter(limit_per_min=100)
    lim.penalise(cooldown_s=30)
    lim.penalise(cooldown_s=0.01)
    with pytest.raises(PlatoError, match="cooling down"):
        lim.acquire(max_wait_s=0.0)


def test_running_out_says_when_to_ask_again():
    """The endpoint turns this into a 503 + retry_after, so the form waits
    instead of showing "couldn't load times"."""
    lim = _RateLimiter(limit_per_min=100)
    lim.penalise(cooldown_s=15)
    with pytest.raises(PlatoThrottled) as exc:
        lim.acquire(max_wait_s=0.0)
    assert 14 < exc.value.retry_after_s <= 15


def test_low_key_wide_budget_holds_bulk_work_but_not_date_clicks():
    """The key is shared with the ingestion jobs, so our own window can look
    empty while Plato is nearly out. Its header is the truth: at the reserve,
    a month crawl stands down and the last requests go to interactive calls."""
    lim = _RateLimiter(limit_per_min=18, bulk_reserve=5)
    lim.observe("4")
    with pytest.raises(PlatoThrottled, match="another caller"):
        lim.acquire(max_wait_s=0.0, bulk=True)
    lim.acquire(max_wait_s=0.0)  # a date click still goes through


def test_healthy_or_missing_budget_header_changes_nothing():
    lim = _RateLimiter(limit_per_min=18, bulk_reserve=5)
    for header in ("12", None, "", "n/a"):
        lim.observe(header)
    lim.acquire(max_wait_s=0.0, bulk=True)


def test_limiter_disabled_when_rate_is_zero():
    lim = _RateLimiter(limit_per_min=0)
    for _ in range(50):
        lim.acquire(max_wait_s=0.0)


# --- bulk paging, range reuse, stale serving ---------------------------------

def _rows(n, day="2026-09-02"):
    return [{"title": f"p{i}", "starttime": f"{day}T10:00:00",
             "endtime": f"{day}T11:00:00", "color": "blue"} for i in range(n)]


def _pages(p):
    return [c[1]["current_page"] for c in p.calls if c[0] == "appointment"]


def test_month_paging_resumes_after_running_out_of_budget():
    """A month Plato can only serve in ~2 minutes must still complete — as a few
    short requests that each keep their progress, not one that hangs."""
    p = FakePlato([_rows(20), PlatoError("budget exhausted"), _rows(20), _rows(5)])
    with pytest.raises(PlatoBusy):
        p.appointments("2026-09-01", "2026-09-30")
    rows = p.appointments("2026-09-01", "2026-09-30")
    assert len(rows) == 45
    assert _pages(p) == [1, 2, 2, 3], "second call resumed at page 2, not page 1"
    assert all(p.bulk_flags), "month paging is bulk work"


def test_a_stale_half_paged_month_starts_over():
    from booking import plato as plato_mod

    p = FakePlato([_rows(20), PlatoError("budget exhausted"), _rows(3)])
    with pytest.raises(PlatoBusy):
        p.appointments("2026-09-01", "2026-09-30")
    began, page, rows = p._partial[("2026-09-01", "2026-09-30")]
    p._partial[("2026-09-01", "2026-09-30")] = (
        began - plato_mod.PLATO_PARTIAL_TTL_S - 1, page, rows)
    assert len(p.appointments("2026-09-01", "2026-09-30")) == 3
    assert _pages(p) == [1, 2, 1], "restarted from page 1 instead of splicing old pages"


def test_a_day_is_answered_from_a_cached_month_with_no_plato_call():
    p = FakePlato([_rows(2, "2026-09-02") + _rows(3, "2026-09-03")])
    p.appointments("2026-09-01", "2026-09-30")
    calls = len(p.calls)
    day = p.appointments("2026-09-03", "2026-09-03")
    assert len(day) == 3 and all(r["starttime"].startswith("2026-09-03") for r in day)
    assert len(p.calls) == calls, "the date click should cost no Plato request"


def test_a_day_outside_the_cached_month_still_fetches():
    p = FakePlato([_rows(1), _rows(1, "2026-10-02")])
    p.appointments("2026-09-01", "2026-09-30")
    p.appointments("2026-10-02", "2026-10-02")
    assert len(p.calls) == 2


def test_fresh_read_skips_the_month_shortcut():
    """The booking re-check must see Plato's current state, not a 90s-old month."""
    p = FakePlato([_rows(1), _rows(1)])
    p.appointments("2026-09-01", "2026-09-30")
    p.appointments("2026-09-02", "2026-09-02", fresh=True)
    assert len(p.calls) == 2
    assert p.bulk_flags == [True, False], "a single day is interactive, not bulk"


def test_an_old_month_is_not_used_to_answer_a_day():
    from booking import plato as plato_mod

    p = FakePlato([_rows(1), _rows(1)])
    p.appointments("2026-09-01", "2026-09-30")
    key = ("2026-09-01", "2026-09-30")
    ts, rows = p._appts_cache[key]
    p._appts_cache[key] = (ts - plato_mod.DAY_FROM_RANGE_MAX_AGE_S - 1, rows)
    p.appointments("2026-09-02", "2026-09-02")
    assert len(p.calls) == 2


def test_failed_refresh_serves_the_last_copy_instead_of_an_error():
    from booking import plato as plato_mod

    p = FakePlato([_rows(2), PlatoError("cooling down after a 429")])
    first = p.appointments("2026-09-01", "2026-09-30")
    key = ("2026-09-01", "2026-09-30")
    ts, rows = p._appts_cache[key]
    p._appts_cache[key] = (ts - plato_mod.APPTS_RANGE_TTL_S - 1, rows)  # expired
    assert p.appointments("2026-09-01", "2026-09-30") == first


def test_fresh_read_never_serves_stale_on_error():
    from booking import plato as plato_mod

    p = FakePlato([_rows(1), RuntimeError("Plato down")])
    p.appointments("2026-09-02", "2026-09-02")
    key = ("2026-09-02", "2026-09-02")
    ts, rows = p._appts_cache[key]
    p._appts_cache[key] = (ts - plato_mod.APPTS_TTL_S - 1, rows)
    with pytest.raises(RuntimeError):
        p.appointments("2026-09-02", "2026-09-02", fresh=True)


def test_a_failed_day_falls_back_to_an_older_cached_month():
    """During a 429 cooldown a date click with no cached day of its own is
    answered from the month we paged a few minutes ago, not an error. Safe:
    the booking re-check reads fresh and refuses a slot that has gone."""
    from booking import plato as plato_mod

    p = FakePlato([_rows(2, "2026-09-02") + _rows(1, "2026-09-03"),
                   PlatoThrottled("cooling down after a 429", retry_after_s=15)])
    p.appointments("2026-09-01", "2026-09-30")
    key = ("2026-09-01", "2026-09-30")
    ts, rows = p._appts_cache[key]
    p._appts_cache[key] = (ts - plato_mod.DAY_FROM_RANGE_MAX_AGE_S - 1, rows)
    day = p.appointments("2026-09-02", "2026-09-02")
    assert len(day) == 2


def test_a_failed_fresh_day_never_falls_back_to_a_cached_month():
    p = FakePlato([_rows(2), RuntimeError("Plato down")])
    p.appointments("2026-09-01", "2026-09-30")
    with pytest.raises(RuntimeError):
        p.appointments("2026-09-02", "2026-09-02", fresh=True)


def test_a_cold_failure_still_raises():
    p = FakePlato([RuntimeError("Plato down")])
    with pytest.raises(RuntimeError):
        p.appointments("2026-09-02", "2026-09-02")


def test_concurrent_identical_fetches_share_one_crawl():
    import threading

    class SlowPlato(FakePlato):
        def get(self, path, params=None, **kw):
            time.sleep(0.15)
            return super().get(path, params, **kw)

    p = SlowPlato([_rows(2)])  # a second fetch would pop an empty queue and fail
    out, errs = [], []

    def run():
        try:
            out.append(p.appointments("2026-09-01", "2026-09-30"))
        except Exception as e:  # pragma: no cover - the failure path under test
            errs.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errs and len(out) == 4
    assert len([c for c in p.calls if c[0] == "appointment"]) == 1


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


# --- Plato's 2026-09-01 response-shape change -------------------------------

WRAPPED_CFG = [{"key": "abc", "active": True, "calendars": GOOD_CFG["calendars"],
                "welcome_title": "Book with Goji"}]


def test_list_wrapped_config_is_unwrapped():
    """Plato changed onlineapptbooking/list from returning the config object to
    returning a list of them. That is what took /book down on 2026-09-01."""
    p = FakePlato([WRAPPED_CFG])
    cfg = p.online_booking_config()
    assert isinstance(cfg, dict)
    assert cfg["calendars"] == GOOD_CFG["calendars"]


def test_bare_object_shape_still_works():
    """Their previous shape must keep working — we don't know which they'll serve."""
    p = FakePlato([GOOD_CFG])
    assert p.online_booking_config() == GOOD_CFG


def test_active_config_wins_over_inactive_ones():
    """Plato allows several booking keys; only the active one is what customers
    see, and it is not necessarily first in the list."""
    inactive = {"key": "old", "active": False, "calendars": []}
    active = {"key": "live", "active": True, "calendars": GOOD_CFG["calendars"]}
    p = FakePlato([[inactive, active]])
    assert p.online_booking_config()["key"] == "live"


def test_falls_back_to_first_entry_with_calendars_when_none_are_active():
    p = FakePlato([[{"key": "x"}, {"key": "y", "calendars": GOOD_CFG["calendars"]}]])
    assert p.online_booking_config()["key"] == "y"


def test_empty_list_is_still_rejected():
    """An empty list carries no calendars — that is a real fault, not a shape
    we should quietly accept."""
    p = FakePlato([[]])
    with pytest.raises(PlatoError, match="malformed booking config"):
        p.online_booking_config()
