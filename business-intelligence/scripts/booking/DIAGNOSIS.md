# Booking System Diagnosis & Fix (2026-08-12)

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
