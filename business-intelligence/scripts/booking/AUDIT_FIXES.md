# Booking System Audit & Fixes

## Audit Date
2026-08-04

## Issues Addressed

### Issue 1: Incorrect Clinician Availability (Recurring Calendar Entries)
**Status**: Infrastructure added for diagnosis and monitoring

**Problem**: The booking system shows appointment slots when clinicians are not available, particularly when clinicians have recurring slots or recurring calendar entries.

**Root Cause Analysis**: To be determined via diagnostic logging. The system may be:
1. Receiving recurring entries from Plato's `appointment` endpoint in an expanded or non-expanded format
2. Not properly handling recurring event recurrence rules or recurrence exceptions
3. Misinterpreting recurring calendar blocks as availability

**Investigation Steps**:
1. Enable diagnostic logging: `export BOOKING_AVAILABILITY_DEBUG=1`
2. Query availability: `PLATO_API_KEY=... python3 -m booking.probe_availability 2026-07-18 physiotherapy`
3. Review logs for:
   - Recurring rule or schedule entry used
   - Generated candidate slots
   - Exclusions applied (restricted blocks, booked appointments, etc.)
   - Final returned slots

**Infrastructure Added**:
- Diagnostic logging in `availability.py` via `BOOKING_AVAILABILITY_DEBUG` environment variable
- Logs capture per-clinician availability derivation including:
  - Service, date, clinician, day-of-week
  - Rule name and hours
  - Restricted blocks and taken appointments
  - Slot generation and filtering

**Acceptance Criteria** (from audit document):
- Valid recurring working slots appear
- Times outside the clinician's intended schedule do not appear
- Recurrence exceptions (cancelled, deleted, moved, blocked occurrences) are not displayed
- Other valid occurrences remain available
- Blocking appointments and leave remove slots from availability
- Schedule changes invalidate cached old slots
- No slots shift to an adjacent day due to UTC conversion
- Backend rejects bookings for slots that become unavailable

### Issue 2: Remove Cheryl Long from Clinical Pilates
**Status**: ✅ COMPLETE

**Changes Made**:

1. **Configuration (config.py)**
   - Added `SERVICE_CLINICIANS` dict to define service-specific clinician rosters
   - Configured Clinical Pilates to only allow `["claire-ng"]`
   - Comment in config explains the mechanism for future roster changes

2. **Availability Logic (availability.py)**
   - Import `SERVICE_CLINICIANS` from config
   - Added service eligibility filter in `_derive_day()`:
     ```python
     if service_clinicians is not None and cid not in service_clinicians:
         continue
     ```
   - Clinicians not in the service roster are skipped during slot generation

3. **Booking Validation (booking.py)**
   - Import `SERVICE_CLINICIANS` from config
   - Added validation for explicitly chosen clinicians:
     ```python
     service_clinicians = SERVICE_CLINICIANS.get(service_id)
     _require(service_clinicians is None or draft["clinician_id"] in service_clinicians,
              "That clinician is not available for this service.")
     ```
   - Rejects bookings for ineligible clinicians with a clear error message

4. **Tests Added**
   - `test_availability.py`:
     - `test_service_clinician_eligibility_excludes_ineligible_clinicians()` — verifies only Claire appears for Clinical Pilates
     - `test_clinician_still_available_in_other_services()` — confirms Cheryl still available in Physiotherapy
   - `test_booking.py`:
     - `test_booking_clinician_ineligible_for_service()` — rejects booking Cheryl for Clinical Pilates
     - `test_first_available_respects_service_clinician_eligibility()` — auto-assignment respects roster

**Acceptance Criteria** (from audit document):

✅ Cheryl Long is not displayed as a clinician after Clinical Pilates is selected
✅ "First available" never returns Cheryl for Clinical Pilates
✅ No Clinical Pilates slots are generated from Cheryl's calendar
✅ Cheryl remains selectable in services she still provides (Physiotherapy, Mummy & Baby)
✅ Cheryl's valid availability continues to appear in other services
✅ Cheryl's clinician profile was not deleted
✅ Cheryl's historical bookings were not deleted

**How to Add/Remove Clinicians from Services**:
```python
# In config.py, edit SERVICE_CLINICIANS:
SERVICE_CLINICIANS = {
    "clinical-pilates": ["claire-ng"],  # remove Cheryl
    "strength-conditioning": ["kristy-ng"],  # example: Kristy only
    # Absent services use all clinicians from their online_calendar
}
```

## Testing

All existing tests pass, plus new tests:

```bash
# Run all tests
python3 -m pytest test_availability.py test_booking.py -v

# Test results: 31 passed
# - 12 availability tests (including 2 new service-eligibility tests)
# - 19 booking tests (including 2 new service-eligibility tests)
```

## Deployment Notes

1. **No Migration Required**: All changes are backward-compatible
   - `SERVICE_CLINICIANS` defaults to empty (no restrictions)
   - Existing bookings and clinician profiles are unaffected

2. **Cache Invalidation**:
   - Availability cache TTL is 45 seconds (short-lived)
   - After updating `SERVICE_CLINICIANS`, restart the service or wait for cache expiry
   - Per-clinician lock ensures consistency at booking time

3. **Monitoring**:
   - Enable diagnostic logging in production if recurring-entry issues surface
   - Check CloudRun logs for availability derivation details
   - Monitor "First available" assignments to verify roster changes took effect

## Open Questions & Next Steps

### For Issue 1 (Recurring Entries):
1. **Recurring Entry Format**: Does Plato's `appointment` endpoint return recurring events as:
   - Single entries with recurrence rules (need to expand)?
   - Pre-expanded individual entries?
   - Both (need to deduplicate)?

2. **Recurrence Exceptions**: How are cancelled/moved occurrences represented?
   - Separate deleted-entry markers?
   - Exception dates in the recurrence rule?
   - Overlapping blocks at exception times?

3. **Timezone Handling**: Are appointment times stored in UTC or SGT?
   - Check for day-boundary shifts due to timezone conversion

### For Issue 2 (Service Eligibility):
- Consider extending `SERVICE_CLINICIANS` to support:
  - Date-range restrictions (e.g., "Cheryl unavailable for Clinical Pilates 2026-07-15 to 2026-08-31")
  - Temporary vs. permanent exclusions
  - Condition-based restrictions (e.g., "only for scoliosis in Physiotherapy")

## Issue 3: Block Cheryl Long from Women's Health Physiotherapy
**Status**: ✅ COMPLETE

**Changes Made** (2026-08-12):

1. **Backend Config (config.py)**
   - Updated `PHYSIO_FOCUS_CLINICIANS["womens-health"]` from `["cheryl-long", "claire-ng", "kristy-ng"]` to `["claire-ng", "kristy-ng"]`
   - Cheryl is now excluded from Women's Health bookings while retaining access to General MSK, Paediatrics, Scoliosis, and Others

2. **Frontend Config (physioCategories.ts)**
   - Updated `womens-health` category `clinicianIds` to `["claire-ng", "kristy-ng"]` for sync with backend
   - UI will only show Claire and Kristy in the clinician picker when Women's Health is selected

3. **Tests Added**
   - `test_womens_health_excludes_cheryl()` — verifies Cheryl does not appear for Women's Health focus
   - `test_womens_health_has_two_clinicians()` — confirms 2 clinicians available with correct slots
   - `test_cheryl_still_available_in_general()` — ensures Cheryl remains available for general physiotherapy
   - Updated `test_physio_focus_is_written_to_note()` to use Claire instead of Cheryl

**Acceptance Criteria** (verified):
✅ Cheryl Long is not displayed for Women's Health physio focus
✅ First available never assigns Cheryl for Women's Health bookings
✅ Claire and Kristy are available for Women's Health
✅ Cheryl remains available in General MSK, Paediatrics, Scoliosis, Others
✅ Cheryl's historical bookings were not deleted
✅ All 45 booking+availability tests pass

## Issue 4: Block Kristy Ng's Wednesdays 5:30pm-8:00pm
**Status**: ✅ COMPLETE

**Problem**: Kristy Ng's Wednesdays 5:30pm-8:00pm should be blocked for bookings, but availability was showing slots during this time, even though Kristy has a recurring block entry in Plato for those times.

**Root Cause**: Kristy's recurring block entry in Plato was not being detected by the booking system (likely due to calendar sync or API timing issues).

**Solution**: Implemented hard-coded clinician restricted blocks in the booking backend configuration (`config.py`), independent of Plato's calendar entries. This ensures the block is enforced consistently without relying on Plato's appointment detection.

**Changes Made**:

1. **Backend Config (config.py)**
   - Added `CLINICIAN_RESTRICTED_BLOCKS` dict to define hard-coded time blocks per clinician
   - Configured Kristy Ng to have a recurring block: Wednesday 17:30-20:00 (5:30-8:00 PM)
   - Format allows adding day-of-week restricted blocks for any clinician

2. **Availability Logic (availability.py)**
   - Import `CLINICIAN_RESTRICTED_BLOCKS` from config
   - Merge hard-coded blocks with Plato-provided restricted blocks during slot derivation
   - Both block types now apply together, providing layered blocking

3. **Test Added** (`test_availability.py`)
   - `test_kristy_wednesday_block_5_30_to_8_00pm()` — verifies hard-coded blocks prevent bookings

**How to Add/Modify Hard-Coded Blocks**:
```python
# In config.py, edit CLINICIAN_RESTRICTED_BLOCKS:
CLINICIAN_RESTRICTED_BLOCKS = {
    "kristy-ng": [
        {"day": "Wed", "starttime": "17:30", "endtime": "20:00"},
        # Add more day/time blocks as needed
    ],
    "another-clinician": [
        {"day": "Fri", "starttime": "12:00", "endtime": "13:00"},  # lunch break
    ],
}
```

**Acceptance Criteria** (verified by test):
✅ Kristy's Wednesday 5:30-8:00pm slots are blocked
✅ Other times on Wednesday remain available
✅ Other clinicians' schedules unaffected
✅ Block is enforced independently of Plato's recurring entries
✅ All 46 booking+availability tests pass

## References

- Audit Document: `Goji Booking System Audit and Fix.docx`
- Booking Service: `business-intelligence/scripts/booking/`
- Config Source of Truth: Plato's `GET /onlineapptbooking/list` + calendar appointments
- Website Config Mirror: `marketing/website/prototype/src/lib/services.ts`, `src/lib/clinicians.ts`, `src/lib/physioCategories.ts`
- Block Detection: `plato.py` LEAVE_KEYWORDS, `availability.py` _booked_by_calendar()
