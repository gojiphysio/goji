# Dashboard Objectives - v1

The single goal of v1 of the Goji BI dashboard is to answer the six questions below. Each section spells out the metric, the data sources, the SQL/transformation logic, and any open gaps.

Cross-references:

- [`schema.md`](schema.md) for the warehouse star schema
- [`../plato-api-docs/`](../plato-api-docs/) for the source API surface
- [`../scripts/probe_output.json`](../scripts/) and `probe2_output.json` for verified data shapes (gitignored - regenerate via `plato_probe.py` and `plato_probe2.py`)

Cross-cutting decisions:

- **Two audiences, two surfaces.** Analytics (aggregate, no PII) and operational (patient names for call lists). Both read the same BigQuery marts; only the operational view exposes PII, and access to it is restricted.
- **Treatment categories live in two places, both useful.** Plato tags every appointment with a treatment type via `code_Bottom` (S&C / Pilates / Physiotherapy / Home Visit). Plato also tags inventory items by `inventory` type. For revenue we use the inventory mapping; for visit counts we use `code_Bottom` directly. No manual mapping table needed for v1.
- **Patient tags ARE a first-class field.** `patient.tag` is an array of `{"tag": "Musculoskeletal"}` records. No need to dig into `patient.custom` or `patient_note` for tagging.

---

## 1. Per-clinician: bookings, revenue, num_appointments

**What the operator sees:** a table or stacked bar by clinician, with three columns - bookings $, recognised revenue $, number of appointments delivered.

**Metric definitions:**

- *Bookings $* - sum of `line_total` from `fct_invoice_line` (classification = booking/sale) where `invoice.doctor` = clinician.
- *Recognised revenue $* - sum of `recognised_revenue` from `fct_service_delivered` where `invoice.doctor` = clinician.
- *Num appointments delivered* - count of `fct_appointment` rows where the appointment occurred in past, joined to the calendar's owner clinician.

**Data sources:**

- `fct_invoice_line` joined to `dim_clinician` via `invoice.doctor` -> `providers.given_id` (codes: PCN, PCL, PKN)
- `fct_service_delivered` (same join)
- `fct_appointment` joined via `appointment.color` -> `calendars.color` -> `calendars.doctor` -> `providers.given_id`

**Status:** READY TO BUILD. The one open question - whether `invoice.doctor` on a redemption matches the actual delivering clinician - resolves in the warehouse once we can SQL-compare doctor codes between source pack invoices and their redemptions. We can also cross-check against `appointment.color` -> `calendar.doctor` for the day of the redemption. If discrepancies show up, we add a CASE WHEN.

---

## 2. Discount cost to the clinic

**What the operator sees:** a number for the period - "$X absorbed in discounts this month" - with a breakdown by clinician and a list of top-discounted invoices.

**Metric definition (provisional):**

```
line_list_value      = item.selling_price * item.qty
line_charged_value   = item.sub_total
line_discount        = MAX(0, line_list_value - line_charged_value)
invoice_adjustment   = invoice.adj_amount    -- only counted when invoice.adj = 1
total_discount       = SUM(line_discount across non-redemption lines) + SUM(invoice_adjustment)
                       over the period
```

**Data sources:**

- `fct_invoice_line.qty`, `selling_price`, `sub_total`, `discount`, `disc_abs`
- Invoice-header: `adj` (boolean flag), `adj_amount` ($)

**Open question / gap:**

The probe didn't surface a real discounted booking (my filter accidentally matched a redemption). To resolve, load all invoices into BQ first, then SQL: `SELECT invoice_id, ... WHERE selling_price > 0 AND sub_total < selling_price * qty AND others.redeem_from IS NULL`. Inspect 2-3 rows to confirm semantics.

The fields `discount` (numeric) and `disc_abs` (0/1 = percentage vs absolute-dollar flag) should not be needed since `sub_total` already reflects the final charge. They're stored anyway for audit.

**Status:** unblocked once data is in BQ; one SQL inspection step required to confirm semantics before claiming the number is final.

---

## 3. Treatment-type breakdown

**What the operator sees:** a pie/bar chart of revenue and visit count by treatment category for a chosen period. Categories from the live data: **S&C, Pilates, Physiotherapy, Home Visit, Product, Voucher**.

**Metric definition - two complementary views:**

For revenue by treatment type, join invoice lines to the inventory mapping below.

For visit count by treatment type, use `fct_appointment.code_Bottom`:

| `code_Bottom` | Treatment type |
|---|---|
| `qLbH` | S&C |
| `2kV4` | Pilates |
| `hDWW` | Physiotherapy |
| `sCla` | Home Visit |

Plus our inventory-side mapping derived from the 28 items we pulled. The category is inferable from `given_id` prefix:

| Prefix pattern | Treatment category |
|---|---|
| `PHY-*`, `MB-*`, `CorpPT` | Physiotherapy |
| `CP1:1-*`, `CP2:1-*` | Clinical Pilates |
| `PP1:1-*`, `PP2:1-*` | Private Pilates |
| `SC-*` | Strength & Conditioning |
| `TBall`, `SBottle`, `GJ-INV-*`, `Mitera*` | Product |
| `Voucher`, `VOU-*` | Voucher |

**Data sources:**

- `fct_invoice_line` for revenue
- `fct_appointment` for visit count (via `code_Bottom`)
- New: `marts.dim_service_category` - tiny BQ view mapping `item_given_id` -> `treatment_category` using the prefix logic above (or a small Google Sheet if your wife wants to edit categories without re-running SQL)

**Status:** READY TO BUILD. All required fields confirmed.

---

## 4. Patient demographics

**What the operator sees:** age band, gender split, top tags, postal sector distribution.

**Confirmed fields on `patient`:**

| Plato field | Use |
|---|---|
| `dob` | derive `age_band` (0-17, 18-29, 30-44, 45-64, 65+) |
| `sex` | gender split (values: "Male", "Female", or empty) |
| `tag[]` | list of `{"tag": "<label>"}`. Examples seen: "Musculoskeletal". Direct ranked count. |
| `postal` | 6-digit Singapore postal code; take first 2 digits for sector |
| `nationality`, `marital_status`, `occupation` | bonus dimensions if you want them |
| `doctor[]` | primary clinician(s) - useful for "patient base by clinician" |
| `referred_by` | acquisition source |
| `corporate[]` | insurance / corporate billing affiliation |

**Data sources:**

- `dim_patient` from `GET /{db}/patient` paginated

**Status:** READY TO BUILD. The earlier worry about `patient.custom` keyed bag is moot - that bag is for custom UI fields and is not the location of tags. Tags are in `tag[]`.

PII handling: `name`, `nric`, `email`, full `address`, `telephone*`, `dob`, `nok` are sensitive. Decision: store these in a separate BQ table `marts.dim_patient_pii` that only the operational dashboard joins to. Analytics views read `dim_patient` (age_band, sex, postal_sector, tag list, primary_doctor only).

---

## 5. Cohort metrics: LTV, repeat visits, retention, churn

**What the operator sees:** new patients per month, % returning at month 1/3/6, average lifetime visits, average lifetime recognised revenue per patient.

**Metric definitions:**

- *LTV* - sum of `recognised_revenue` per patient over their entire history.
- *Repeat visits* - count of distinct visit dates (`fct_service_delivered.delivery_date`) per patient.
- *Retention (month N)* - among patients whose first visit was in cohort month M, % with at least one delivered service in month M+N.
- *Churn (90-day)* - % of patients with no delivered service in last 90 days, among those active 90-180 days ago.

**Data sources:**

- `fct_service_delivered` joined to `dim_patient`
- `dim_patient.first_visit_date` (derived as MIN of delivery_date per patient)

**Status:** READY TO BUILD. Single dependency: a one-time historical backfill of ALL invoices (no `modified_since` filter on first load). Clinic is new (~6 weeks of data based on first patient created_on of 2026-04-29) so the backfill is small - probably 1000-2000 invoices total.

---

## 6. Unconfirmed upcoming appointments worth chasing

**What the operator sees:** a list of future appointments where the patient hasn't confirmed yet, ranked by how soon they are. Operator uses this list for confirmation calls.

(Originally Q6 was "last 30 days cancellations" - dropped from v1 because Plato cancellations are hard-deletes, captured only via webhook, and there are no SOPs in place yet to track cancellations cleanly. Forward-looking confirmations are more actionable for a new clinic.)

**Metric / view definition:**

```sql
SELECT
  appointment_date,
  appointment_time,
  hours_until_appointment,
  clinician_name,
  treatment_type,                  -- from code_Bottom
  patient_name,
  patient_phone,
  appointment_id
FROM fct_appointment a
JOIN dim_patient_pii p USING (patient_id)
JOIN dim_clinician c ON c.calendar_color = a.color
WHERE a.code_Left = 'C22K'         -- Unconfirmed
  AND a.starttime >= CURRENT_TIMESTAMP()
  AND a.starttime <= CURRENT_TIMESTAMP() + INTERVAL 7 DAY
ORDER BY a.starttime ASC;
```

**Data sources:**

- `fct_appointment` (with `code_Left` and `code_Bottom` preserved)
- `dim_clinician` (calendar -> doctor join)
- `dim_patient_pii` (the PII-bearing patient view for the operational dashboard)

**Confirmed Plato code mappings (from probe2):**

| Field | Value | Meaning |
|---|---|---|
| `code_Left` | `YS06` | Confirmed |
| `code_Left` | `C22K` | Unconfirmed |
| `code_Bottom` | `qLbH` | S&C |
| `code_Bottom` | `2kV4` | Pilates |
| `code_Bottom` | `hDWW` | Physiotherapy |
| `code_Bottom` | `sCla` | Home Visit |

**Status:** READY TO BUILD. Lives in the operational (PII-allowed) dashboard.

**Future: cancellation dashboard (v1.5+ if needed):** Plato hard-deletes cancellations and the only signal is the `appointment:delete` webhook. Defer until (a) the clinic has cancellation-handling SOPs in place and (b) we have a Cloud Run HTTPS webhook receiver running. Don't build half a solution.

---

## Summary of open data gaps - status post-probe2

| Gap | Status | Action |
|---|---|---|
| Condition tags location | **RESOLVED** - `patient.tag[]` is the field | None |
| Treatment category mapping | **RESOLVED** - inventory prefix + `appointment.code_Bottom` | None |
| Discount semantics | Mostly clear from field shapes; needs one SQL inspection of a real discounted booking once loaded | Inspect in BQ |
| Cancellation signal | **CRITICAL** - hard-delete only; webhook required | Defer cancellation tile to v1.5 (post-GCP + Cloud Run webhook) |
| Full queue status list | **RESOLVED** - 4 statuses: Checked In, Consult Start, Consult End, Checked Out | None |
| Selling vs delivering clinician | Resolve via SQL join once all invoices loaded. To fetch a specific invoice via API, use `GET /{db}/invoice?invoice_id={id}` (filter on the list endpoint - there is no GET-single-invoice endpoint) | Inspect in BQ |

## What this changes for v1 build order

1. Resume GCP setup (Task #18) - install gcloud, create project, enable BQ.
2. Build the loader to do a **full historical backfill** of invoices (no `modified_since` on first run; clinic is ~6 weeks old so total volume is small). Pull both invoices and appointments fully.
3. Once data is in BQ, run two SQL inspection queries: (a) find a discounted booking and confirm `sub_total` semantics; (b) compare `invoice.doctor` between redemptions and their source packs.
4. Build the analytics dashboard with questions 1-5 (per-clinician, discounts, treatment mix, demographics, cohorts).
5. Build the operational dashboard for Q6 (unconfirmed upcoming appointments worth chasing).

**Useful Plato API parameters discovered (not used yet but worth remembering):**

- `GET /{db}/invoice` accepts `start_date`, `end_date` (YYYY-MM-DD), `patient_id`, `invoice_id`, `invoice` (number), `modified_since` (Unix timestamp per spec, though our string dates have been working), `include_drafts` (default false).
- For date-bounded loads, prefer `start_date`/`end_date` over client-side filtering - server-side is cheaper on rate limits.
