# Dashboard roadmap

## ✅ Phase 1 — Subdomain split + auth (done)

- `dashboard.gojiphysio.com` — founders/finance only (`APP_MODE=dashboard`)
- `frontdesk.gojiphysio.com` — whole team: reception + clinicians (`APP_MODE=frontdesk`)
- Multi-staff credentials: `STAFF_USER/PASS` (shared legacy) + `STAFF_<N>_USER/PASS`
  per person (format `firstnamelastname`, e.g. `claireng`)
- Founder credential is a skeleton key — works on both subdomains
- `deploy_frontdesk.sh` — one-command deploy for the front desk service

---

## ✅ Phase 2 — Today's Schedule on `frontdesk.*` (done, then partly reverted)

> **Stale below.** `fct_upcoming_appointments` and `appt_confirmation_events`
> described in this phase were **removed** by `7361f8b` ("Front desk: drop
> Plato-mirror tabs, add WhatsApp/Instagram Leads pipeline"). What survives is the
> new-patient welcome worklist (`fct_new_patient_welcome` +
> `new_patient_welcome_events`) and its "Next 48 hours" tab. Kept for the
> reasoning, not as a description of the code.


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

### Marketing tab — DONE (founder-only) / follow-ups

The **Marketing** tab now ships on `dashboard.*` (founder-only — the `marketing`
read-only role above is still the future split). It presents the clinic numbers
through a marketing lens (north-star KPIs, acquisition, delivery-lane mix,
ICP/clinical-focus, referral sources). The static 90-day-plan operating tools
(weekly rhythm, content calendar, partnership pipeline, manual enquiry log) were
removed once the plan lapsed — inbound inquiries now live in the front-desk
Leads pipeline (`marts.lead_events`). Open follow-ups:

- **Marketing tab redesign — DONE.** The tab is now ordered by decision
  hierarchy: north stars (active + new patients, one range-bucketed chart; Revenue
  dropped from this tab) → top-of-funnel channels (Instagram promoted to
  reach + profile visits + follower growth) → cleaner acquisition Sankey →
  **on-site path & booking drop-off** (per-page attribution from the beacon's
  `landing_path`, plus booked / bailed-to-WhatsApp / dropped for booking-page
  sessions via the on-site CTA `?sid=&p=` passthrough) → base/ICP/referral lenses.
- **Channel integrations** (the remaining WIP cards): Google Business Profile
  clicks/calls, website sessions (GA4/PostHog), paid spend + cost-per-first-visit,
  review velocity. Instagram is live (reach + profile views + followers). Each
  card is the seam to plug into.
- **Enquiry → first-visit attribution**: Plato only records a coarse
  `referred_by` per patient, so first visits can't be split by marketing channel
  today. The front-desk Leads pipeline is the manual bridge; later, tag enquiry
  source at intake and flow it into the warehouse to close the loop per channel.

---

## Phase 4 — WhatsApp leads funnel tracking (idea / to-do)

### Goal

WhatsApp is the primary CTA — customers message us before they book — but once a
message lands there's no structured record of it. We want to **organise and track
each inbound WhatsApp lead through the sales funnel** so we can answer:

- How many inquiries come in (per week / channel)?
- How many convert to a booked first visit (close rate)?
- How many go cold / are lost, and at what stage?
- Where in the funnel do we leak, and how fast do we respond?

This closes the loop the Phase 3 follow-up flags: the public redirector already
logs the **click** (`go.gojiphysio.com/<slug>` → `record_link_click`), but not
what happens after the WhatsApp conversation starts. A lead pipeline is the
missing middle between "click logged" and "first visit in Plato".

### Funnel stages (straw model — refine before building)

`inquiry → qualified → booked → showed (first visit) → won` , with `lost`
(+ reason) reachable from any stage. Mirrors the existing append-only
event-log pattern (`patient_followup_events`, `appt_confirmation_events`).

### Sketch (follows established patterns — not a commitment)

- **New append-only table** `marts.whatsapp_lead_events` (lead_id, stage,
  source_slug, notes, staff, event_ts) + a `_latest` view for current stage per
  lead. Add it to the `dataEditor` grant loops in `deploy_admin.sh`, `DEPLOY.md`,
  and `.github/workflows/deploy-dashboard.yml`.
- **New mart** `fct_lead_funnel` — counts by stage + conversion/loss rates per
  period, to back glanceable funnel cards (reuse `renderTrend`).
- **Frontdesk surface** to capture/advance a lead (a tab in `admin.html`, gated
  `@require_roles("founder", "staff")`), since reception works the WhatsApp inbox.
- **Founder/Marketing surface** for the funnel headline metrics (close rate,
  lost-reason mix) — likely a card group on the Marketing tab.

### Open questions before starting

- **Capture method.** Manual entry by reception (fastest to ship, fits the
  follow-up-log precedent) vs. some WhatsApp Business API ingestion (richer, but
  Meta API + opt-in overhead — weigh against the "free / DIY first" rule). Start
  manual, leave the API as a later seam?
- **Lead ↔ patient join.** How do we link a WhatsApp lead to the eventual Plato
  patient to confirm "won" automatically? Phone number is the natural key — is it
  reliably captured on both sides?
- **Dedup / identity.** One person messaging twice shouldn't double-count
  inquiries — key on phone, not message.

---

## Phase 5 — Google Ads relaunch prep (idea / to-do)

### Goal

The Google Ads campaign was suspended for underperforming (spend went to brand +
junk queries, not high-intent searches — see `marketing/ads/google-ads-playbook.md`).
Before relaunching, put the few numbers we'd otherwise open the Google Ads UI for
**on the Marketing tab**, so the founder can steer the relaunch from one place.

> The relaunch itself is specced in `marketing/ads/google-ads-campaign-plan.md`
> (2026-07). Note its final-URL suffix adds `utm_term={keyword}`, so
> `marts.web_session_events.utm_term` now carries the matched keyword —
> keyword→session→booking joins work today, before these transfer views land.

### What to surface (from the BQ Data Transfer `google_ads` dataset)

`fetch_google_ads` already reads campaign/account stats. Add sibling graceful-
degradation fetches (same shape) reading the transfer's keyword/search-term views:
- **Routing keywords** — the keywords actually serving us (`keyword_view` /
  `ad_group_criterion`): keyword, match type, impressions, clicks, cost, conv.
- **Top search terms** — the real queries coming in (`search_term_view`): term,
  clicks, cost, whether it converted. This is where brand/junk shows up.
- **Expert additions** (all cheap once the views are in the transfer):
  - **Brand vs non-brand split** of spend & conversions (regex on the term/keyword
    against the brand words) — the exact leak that got us suspended.
  - **Search-term → booking conversions** — join the `booking_confirmed`
    conversion (already fired site-side, see the playbook §6) back to the term, so
    we optimise toward booking-producing queries, not cheap clicks.
  - **Wasted-spend list** — terms with spend but zero conversions → negative-
    keyword candidates (surface as a "consider excluding" list).
  - **Impression share / lost-to-budget** if the transfer exposes it — are we
    capped by budget or rank on the terms we want?

### Notes before starting

- Cards stay **inert/graceful** until the transfer includes the keyword +
  search-term views (the transfer config may need those tables enabled) — same
  "WIP seam → live card" pattern as the other channel integrations.
- Keep it a **read-only lens**: the actual keyword/negative/bid changes happen in
  the Google Ads UI per the playbook; the dashboard just tells us *what* to change.
- The `google_ads` dataset is **US region** — query it directly (a mart view can't
  cross regions), exactly like `fetch_google_ads` does today.

---

## ✅ Phase 6 — Automated 48-hour appointment reminders (done)

### Goal

Stop someone having to log into Plato every day to fire the reminder template by
hand. Plato's API has no notification/template endpoint, so we send it ourselves.

### What shipped

- `marts.fct_appointment_reminders` — who to remind (D+2 calendar date, PII-free,
  reusing the appointment qualifier + ghost guard from `fct_new_patient_welcome`).
- `marts.appointment_reminder_events` (+ `_latest`) — append-only send ledger and
  idempotency guard.
- `scripts/reminders/` — the `appointment-reminders` Cloud Run Job. Reads marts,
  sends over Gmail SMTP as `hello@gojiphysio.com`, one email per patient per day.
- Cloud Scheduler `appointment-reminders-daily`, 12:00 SGT, all 7 days.
- `reminder-wa` link slug so reminder-driven WhatsApp traffic is attributable.

Notes: `scripts/reminders/README.md`, ops in `DEPLOY.md`.

### Deliberately not done

- **WhatsApp.** Every strategy doc calls it the SG default (~98% open vs ~20%
  email), but it needs Meta Business verification and a pre-approved UTILITY
  template. Email is the channel that already worked end-to-end, so it shipped
  first. The job groups recipients before sending, so a second channel slots in
  at the send step.
- **A Front Desk "Reminders" tab.** Patients with no email are digested to
  `hello@` instead. Build the tab if the digest turns out to be ignored.

### Watch

- **Email coverage was the near-miss here.** Measured at build time, only
  **4 of 91** upcoming appointments (4.4%) carried an inline email — an address
  lands on the payload only when the front desk types one in, and every booking
  in the window was manual rather than from the website form. The Plato *profile*
  has an email for nearly everyone, so `plato_patients` was extended with
  `extract_email()` and `dim_patient_contact` gained an `email` column. Confirm
  actual coverage from the first dry-run digests rather than assuming it worked.
- If the unreachable list is still large, ~90% of patients are reachable by phone
  via the profile — that's the argument for bringing the WhatsApp phase forward.
- **`dnd` on the Plato patient record is deliberately ignored.** A 48-hour
  reminder is transactional, not marketing. Revisit if outbound marketing is ever
  added here — and note the flag exists, since it may be the "Contactability"
  concept the repo docs reference but never built.

