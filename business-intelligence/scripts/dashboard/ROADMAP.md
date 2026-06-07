# Dashboard roadmap

## ✅ Phase 1 — Subdomain split + auth (done)

- `dashboard.gojiphysio.com` — founders/finance only (`APP_MODE=dashboard`)
- `frontdesk.gojiphysio.com` — whole team: reception + clinicians (`APP_MODE=frontdesk`)
- Multi-staff credentials: `STAFF_USER/PASS` (shared legacy) + `STAFF_<N>_USER/PASS`
  per person (format `firstnamelastname`, e.g. `claireng`)
- Founder credential is a skeleton key — works on both subdomains
- `deploy_frontdesk.sh` — one-command deploy for the front desk service

---

## ✅ Phase 2 — Today's Schedule on `frontdesk.*` (done)

### Goal

Replace the need to keep Plato open separately. Front desk (and clinicians) see
today's appointments in one place, with new-patient flags and confirmation status.

### What shipped

- New marts: `fct_upcoming_appointments` (today + next 72h, PII-free),
  `fct_package_balance` (prepaid sessions left per patient), and the append-only
  `appt_confirmation_events` table (+ `appt_confirmation_latest` view). All
  picked up automatically by `deploy_all.sh`.
- Routes in `app.py`: `GET /api/admin/schedule`, `GET /api/admin/calls`,
  `GET /api/admin/package_alerts`, `POST /api/admin/confirm_appt` — all gated
  `@require_roles("founder", "staff")`. Name/phone hydrated from
  `marts.dim_patient_contact` at render time, never stored.
- `admin.html` now has four top-level tabs: **Today**, **Call list**,
  **Package alerts**, **Retention**.
- `deploy_admin.sh` grants the dashboard SA table-level `dataEditor` on
  `appt_confirmation_events` (alongside the existing follow-up table).

**Open question — resolved.** Data freshness: a ≤15-min lag from Plato is fine
for a same-day schedule, so the schedule reads BigQuery as-is (no live Plato
fetch). **Sessions-remaining caveat:** pack size is read from the SKU
(`-NN` suffix); patients holding a package whose pack size isn't encoded are
left off Package Alerts rather than shown a guessed count — fold in a pack-size
reference table to make every package exact.

### Original plan (for reference)

### 1. New BigQuery mart: `fct_upcoming_appointments`

File: `business-intelligence/scripts/sql/marts/fct_upcoming_appointments.sql`

```sql
-- Grain: one row per appointment for today + next 72 hours
-- Join: stg.appointments × dim_clinician × dim_patient
-- Include: package sessions remaining (from fct_service_delivered)
-- PII: initial_lastname only (same pattern as fct_patient_retention)
--       full name + phone hydrated live from dim_patient_contact at render time
SELECT
  a.appointment_id,
  a.appointment_datetime,
  a.patient_id,
  a.clinician_id,
  a.service_name,
  a.status,          -- 'confirmed' | 'unconfirmed' | 'cancelled'
  p.initial_lastname,
  p.age_band,
  p.first_visit_date = DATE(a.appointment_datetime) AS is_first_visit,
  COALESCE(pkg.sessions_remaining, 0)               AS sessions_remaining
FROM stg.appointments a
JOIN dim_patient p USING (patient_id)
LEFT JOIN (
  -- sessions remaining per patient: sold - delivered
  ...
) pkg USING (patient_id)
WHERE DATE(a.appointment_datetime) BETWEEN CURRENT_DATE() AND CURRENT_DATE() + 3
```

Add to `business-intelligence/scripts/sql/deploy_all.sh` so it deploys with the rest.

### 2. New Flask routes in `app.py`

```python
GET  /api/admin/schedule    # today's appointments (time-ordered)
GET  /api/admin/calls       # unconfirmed appts in next 72h
GET  /api/admin/package_alerts  # patients with ≤2 sessions remaining
POST /api/admin/confirm_appt    # mark an appointment confirmed
                                # → appends to appt_confirmation_events table
```

All gated `@require_roles("founder", "staff")`.

PII hydration: same pattern as the retention worklist — query
`marts.dim_patient_contact` for name + phone by patient_id list at render time.

### 3. New tabs in `admin.html`

Add three tabs alongside the existing **Retention** tab:

**Today** tab
- Time-ordered appointment list
- Badges: `NEW` (first visit), `UNCONFIRMED`
- Clinician filter (All / Claire / Cheryl / Kristy)
- Each row: time · patient name · clinician · service · session balance

**Call List** tab
- Unconfirmed appointments in next 72h
- Columns: appt datetime · patient name · phone · clinician
- One-click **Confirm** button → POST `/api/admin/confirm_appt`

**Package Alerts** tab
- Patients with 0–2 sessions remaining, sorted by urgency (0 first)
- Columns: patient name · clinician · sessions left · last visit

### 4. New BQ table: `appt_confirmation_events`

Append-only event log (same pattern as `patient_followup_events`):

```sql
CREATE TABLE IF NOT EXISTS marts.appt_confirmation_events (
  event_id      STRING NOT NULL,
  appointment_id STRING NOT NULL,
  confirmed_by  STRING,
  confirmed_at  TIMESTAMP NOT NULL
)
```

Dashboard SA needs `roles/bigquery.dataEditor` on this table (same grant as
`patient_followup_events` — add to `deploy_admin.sh`).

### Open question before starting

**Data freshness**: `stg.appointments` ingests every 15 minutes from Plato.
Is a 15-min lag acceptable for the schedule view?
- If yes → use BQ as-is (simpler).
- If no → add a live Plato fetch path for appointment status (same pattern as
  the name/phone hydration already in `app.py`, hitting `GET /{db}/appointments`).

---

## Phase 3 — Founder enhancements on `dashboard.*`

- Package liability aging — deferred revenue bucketed by staleness (packs sold
  >30/60/90d ago with unused sessions)
- Slot utilisation rate — sessions booked / available capacity
- `marketing` role — tab-gated read-only access to Demographics, Referrals,
  Treatment Mix, Cohort on `dashboard.*`; no P&L or commission
- Xero integration — true net margin, payroll, rent, supplies (blocked on Xero)
