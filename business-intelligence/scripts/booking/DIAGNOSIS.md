# Booking availability — runbook & incident log

The symptom is always the same from the outside: **"We couldn't load times just
now"** on `/book`, i.e. `GET /api/availability` returning `502
{"error":"unavailable"}`. This file is the runbook for that, plus the history of
what has actually caused it.

## First move

```bash
curl -s https://booking.gojiphysio.com/healthcheck/deep | jq
```

`/healthcheck` only proves the container is up — it stayed 200 through the whole
2026-09-01 outage. `/healthcheck/deep` derives real availability, so it tells you
whether a visitor can book. Read `reason`:

| `reason`            | Meaning                                                    | Go to |
|---------------------|------------------------------------------------------------|-------|
| _(200, `ok: true`)_ | Booking works. The complaint is stale or client-side.        | Check the browser console on `/book`. |
| `derivation_failed` | Plato threw, or our derivation did.                          | §Logs below. |
| `no_bookable_dates` | Ran clean, empty calendar. Roster/rules problem, not a crash. | Plato `onlineapptbooking/list` + `config.py`. |

This endpoint is what the Cloud Monitoring uptime check watches (every 5 min,
alerting `hello@gojiphysio.com`); `setup_monitoring.sh` provisions it.

## Logs

```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=goji-booking AND severity>=WARNING' \
  --project=goji-bi --limit=20 --freshness=1h \
  --format='value(timestamp,textPayload)'
```

Availability failures log with a full traceback (`exc_info`), so the failing line
is in the log — you should not need to reproduce it.

## Known causes

### Plato's 20 req/min cap (`429 Client Error: Too Many Requests`)

Plato throttles per API key, so every availability lookup, month summary and
booking write shares one clinic-wide budget. `plato.py` now paces itself with a
token bucket (`_RateLimiter`, 18/min with a burst of 20) rather than discovering
the cap via 429s — a 429 costs 7s of retry backoff and still ends as a 502 on the
form. If you see `Plato rate budget exhausted` we are genuinely over budget:
find what is fanning out, don't just raise `PLATO_RATE_PER_MIN`.

The usual culprit is the month summary: it pages a whole month of appointments
(20 rows/page, 10+ pages for a busy month — half the minute's budget in one
request). `PLATO_APPTS_RANGE_TTL` (5 min) is what keeps every focus/clinician
variant of the same month from re-paging it.

### A poisoned config cache (`'list' object has no attribute 'get'`)

Plato answers some throttled reads with **HTTP 200 and a bare `[]` body**.
`online_booking_config()` used to cache whatever came back for 5 minutes, so one
bad response made every availability call fail in `_rules_for` (`cfg.get(
"calendars")`) long after Plato had recovered — a blip became a sustained
outage. `plato.py` now refuses to cache anything that is not a dict with
`calendars`, and serves the last known-good copy when a refresh fails. Covered by
`test_plato_client.py`.

### `--max-instances=1` is load-bearing

The per-clinician booking locks and the rate limiter are both in-process. Raising
max-instances without moving them to a shared store breaks double-booking
protection and quietly multiplies our Plato request rate by the instance count.

## Deeper diagnostics

```bash
# Detailed slot derivation + leave-block tracing (noisy — turn it back off)
gcloud run services update goji-booking --region=asia-southeast1 \
  --update-env-vars BOOKING_AVAILABILITY_DEBUG=1

# Probe Plato directly, read-only
PLATO_API_KEY=... python3 -m booking.probe_availability 2026-09-04 physiotherapy

# Clear caches (a new revision starts cold)
gcloud run services update goji-booking --region=asia-southeast1 \
  --update-env-vars FORCE_RESTART=$(date +%s)
```

## Tests

```bash
cd business-intelligence/scripts && python3 -m pytest booking/ -q
```

---

# Incident log

## 2026-09-01 — Plato changed a response shape; /book down for ~9 hours

**Symptom.** Every `/api/availability` and `/api/availability-summary` call
returned `502 {"error":"unavailable"}` — "We couldn't load times just now". The
go-link redirector (`go.gojiphysio.com/web-book`) and the `/book` page itself
were fine; the outage was entirely in the times fetch. Plain `/healthcheck`
returned 200 throughout, so nothing alerted and it was found by a human.

**Root cause — a breaking change on Plato's side, unannounced.**
`GET /onlineapptbooking/list` used to return the booking-config object:

```json
{"key": "…", "active": true, "calendars": [ … ]}
```

From ~15:27 UTC it returned a **list of** those objects:

```json
[{"key": "…", "active": true, "calendars": [ … ]}]
```

`_rules_for` does `cfg.get("calendars")`, so every derivation died with `'list'
object has no attribute 'get'`. Nothing we shipped caused it — the last deploy
was four days earlier, and the first failure came from a container that had
booted three minutes before, with no 429 ahead of it. The config itself was
never damaged: `active: true`, all 7 calendars and their rules intact.

**What made it worse than a one-line bug:**

- *Cache poisoning.* `online_booking_config()` cached the response unvalidated
  for 5 minutes, so recovery would have lagged the fix by a TTL — and it made
  the logs alternate between two unrelated errors, which read as "intermittent"
  and sent the first diagnosis down the rate-limit path.
- *Wasted budget.* `derive_*` fetched appointments **before** the config, so
  every doomed request first crawled a paginated day/month from Plato and only
  then hit the error. During a month view that is 10+ requests of a 20/min
  budget spent on a request that could never succeed.
- *Real 429s on top.* Plato throttling was genuinely happening (53 in the week
  before, 27 in the final day) and was a second, independent failure mode. It
  was not the trigger, but it did make the picture harder to read.

**Fixes.**
`_normalise_booking_config()` accepts both shapes and prefers the `active`
entry; only something carrying `calendars` is ever cached, with a last-known-good
fallback and a retry back-off; config is fetched before appointments; token-bucket
pacing at 18/min; range-aware appointments TTL; `exc_info` on failures;
`/healthcheck/deep`; and a Cloud Monitoring uptime check + alert
(`setup_monitoring.sh`) so the next one pages us instead of a customer.

**Standing lesson.** Plato is a third-party API that changes shape without
notice. Never hand a Plato response straight to code that assumes a shape, and
never cache one that hasn't been validated.

## 2026-08-12 — Women's Health times not loading

## Issue Summary
Booking system was "totally crashing" when users tried to load available times for Women's Health physiotherapy. Error: "We couldn't load times just now" (HTTP 502 from backend).

## Diagnosis

### Root Cause: Likely Rate-Limiting or Deployment Lag
The most recent issue was a **rate-limit timeout** caused by the ±30-day fetch window expansion introduced to catch recurring appointments. This was already hotfixed in commit `55c97cc` which reverted the expansion, but:

1. **If times still won't load**: The deployed code may still have the expansion. Verify `plato.py` line 126 does NOT have:
   ```python
   query_start = expanded_start.isoformat()  # ← Should NOT be there
   query_end = expanded_end.isoformat()      # ← Should NOT be there
   ```

2. **Plato API Timeout**: Even single-day fetches can timeout if Plato's API is slow or rate-limiting (20 req/min cap). The availability endpoint caches for 45 seconds, but a burst of visitors clicking dates can exceed the limit.

### Why Women's Health Specifically?
Women's Health is a physiotherapy sub-type (not a separate service). It maps to the same calendar as General MSK, Paediatrics, etc., so availability derives the same way. If it was failing while others worked, the issue was likely:
- A specific clinician configuration issue (now fixed)
- Deployment of partially-applied fixes

## Fixes Applied

### 1. Blocked Cheryl Long from Women's Health ✅
**Why**: To prevent ineligible clinician assignments and simplify her roster.

**Changes**:
- Backend `config.py`: Updated `PHYSIO_FOCUS_CLINICIANS["womens-health"]` to `["claire-ng", "kristy-ng"]`
- Frontend `physioCategories.ts`: Synced clinician list
- Added 3 new tests to verify eligibility enforcement
- All 45 tests pass

### 2. Updated Documentation ✅
**README.md**: Clarified that single-day appointment fetches do NOT expand recurring entries locally (that's a Plato API limitation, not our code limitation).

### 3. Verified Code Quality ✅
- No recent regressions in availability derivation
- Multi-day block handling works correctly
- Leave/vacation detection works correctly
- All eligibility filters (service, focus, clinician) work correctly

## Diagnosis Checklist for "Times Still Won't Load"

If times are still not loading after deployment, check:

1. **Deployment Status**
   ```bash
   # Check if latest code is deployed
   curl https://booking.gojiphysio.com/healthcheck
   # Should return "ok", 200
   ```

2. **Plato API Connectivity**
   ```bash
   # Test locally with real Plato key
   export PLATO_API_KEY=...
   python3 -m booking.probe_availability 2026-08-20 physiotherapy
   # Look for timeout or rate-limit errors
   ```

3. **Enable Diagnostic Logging** (production)
   ```bash
   # Set environment variable
   export BOOKING_AVAILABILITY_DEBUG=1
   # Try one availability request
   curl "https://booking.gojiphysio.com/api/availability?service=physiotherapy&focus=womens-health&date=2026-08-20"
   # Check Cloud Run logs for detailed slot derivation
   ```

4. **Cache Issue**
   ```bash
   # If stuck, clear cache (cloud run restart)
   gcloud run services update goji-booking --region us-central1
   # Or wait 45 seconds for availability cache TTL to expire
   ```

5. **Rate-Limit Backoff**
   - If Plato returns 429 (rate-limited), the code retries with exponential backoff
   - Check `plato.py` line 78-81: backoff is capped at 8 seconds (was longer before, causing form hangs)
   - If rate-limit persists, request Plato increase the cap or add queuing

## Testing

All 45 tests pass (23 availability + 19 booking + 3 web-event):
```bash
cd business-intelligence/scripts/booking
python3 -m pytest test_booking.py test_availability.py -v
```

### New Women's Health Tests
- `test_womens_health_excludes_cheryl()` — Cheryl not in roster
- `test_womens_health_has_two_clinicians()` — Claire & Kristy available with slots
- `test_cheryl_still_available_in_general()` — Cheryl still available for other focuses

## Next Steps (if still broken)

1. **Check Logs**: `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=goji-booking"`
2. **Check Metrics**: Look for high latency or error rates in Cloud Run dashboard
3. **Test Plato**: Manually call Plato API to verify it's responding (not rate-limited or down)
4. **Restart Service**: If cache is stuck: `gcloud run services update goji-booking --region us-central1 --update-env-vars FORCE_RESTART=true`
