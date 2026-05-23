# Goji BI - Schema

Last updated: 2026-05-23

This is the canonical schema for the Goji Physiotherapy BI warehouse. It supersedes any earlier sketches in chat.

## Naming and layering

Three BigQuery datasets, one per layer:

- `raw` - exact landings from source APIs, append-only, JSON-friendly. Never queried by dashboards.
- `stg` - typed, deduped, source-shaped views. Light transformations only.
- `marts` - the star schema below. This is what Looker Studio points at.

Every table carries `_loaded_at` (UTC timestamp of the row's most recent load) and, where applicable, `_source_modified_at` (the API's `modified_since` value the row came back with).

## The booking vs. revenue distinction

Goji sells multi-session packages (e.g. 10-packs of physio). Cash and revenue diverge in time:

| Event | When | Fact table | Money concept |
|---|---|---|---|
| Booking | Patient buys a pack or single visit. Invoice finalized. | `fct_invoice_line` | Cash in (sale) |
| Service delivery | Patient attends a session. Pack decremented by 1. | `fct_service_delivered` | Revenue recognised |
| Deferred liability | Difference between cash collected and revenue earned, as of a date. | `fct_package_balance` (daily snapshot) | Liability on balance sheet |

For a single-session sale, all three collapse to the same moment - `booking == recognised revenue`, `deferred = 0`. Complexity is only in packages.

## Dimensions

### `dim_date`

Seeded for 2020-2035.

| Column | Notes |
|---|---|
| `date` (PK) | |
| `dow`, `dow_name` | 1=Mon..7=Sun |
| `iso_week`, `iso_year` | |
| `month`, `month_name`, `quarter`, `fy` | FY mapped to clinic's tax year |
| `is_weekend`, `is_public_holiday` | Singapore public holidays |

### `dim_clinician`

Sourced from Plato `/systemsetup`. **Two related fields, both useful:**

- `systemsetup.providers[]` - the clinician roster. Each has `given_id` (e.g. `PCN`), `name` (e.g. "Claire Ng"), `qual`, `mcr` (Medical/AHPC registration).
- `systemsetup.calendars[]` - the bookable calendars. Each has `color` (the calendar id used on appointments, e.g. `"blue"`), `name`, `doctor` (the `given_id` from providers), `location`.

The appointment's `color` field equals `calendars[].color`, which then resolves to `calendars[].doctor` which equals `providers[].given_id`. So:

| Column | Notes |
|---|---|
| `clinician_id` (PK) | provider `given_id`, e.g. `PCN` |
| `full_name` | provider `name`, e.g. "Claire Ng" |
| `calendar_color` | the corresponding `color` value on calendars (joins to appointments) |
| `qualifications` | provider `qual` (HTML, often includes registration body) |
| `registration_number` | provider `mcr` (AHPC for Singapore physios) |
| `role` | physio / massage / admin (derive from name/qual if not in API) |
| `employment_type`, `fte`, `comp_model`, `hire_date`, `status` | manual; not in Plato API. Maintain in a `marts.dim_clinician_overrides` table. |
| `simultaneous_capacity` | usually 1; rooms supporting parallel sessions >1 |

Confirmed roster (3 active providers as of 2026-05-23): PCN (Claire Ng), PCL (Cheryl Long), PKN.

### `dim_patient`

PII-safe. Sourced from `/patient`.

| Column | Notes |
|---|---|
| `patient_id` (PK) | Plato ID |
| `age_band` | 0-17, 18-29, 30-44, 45-64, 65+ |
| `gender` | |
| `postcode_sector` | first 2 digits of Singapore postal code (the sector identifier) - enough for catchment analysis without re-identifying patients |
| `referral_source` | |
| `first_visit_date` | derived |
| `lifetime_visits`, `lifetime_revenue` | derived, updated nightly |
| `is_active` | visited in last 90 days |

We do NOT store name, full DOB, address, phone, email in the warehouse. Patient identification stays inside Plato.

### `dim_service` (= Plato inventory catalogue)

This is the foundation for the booking/revenue split.

| Column | Notes |
|---|---|
| `item_id` (PK) | Plato `given_id` |
| `name` | "Initial Physio Consult", "10-Pack Physio", etc. |
| `category` | consult / treatment / package / product / other |
| `is_package` | bool |
| `sessions_per_pack` | int, NULL when `is_package = false` |
| `per_session_value` | list_price / sessions_per_pack for packs; list_price for single-use |
| `list_price` | |
| `revenue_recognition` | `on_sale` (single visits, products) or `on_delivery` (packages, deposits) |
| `tax_code` | for Singapore GST mapping to Xero (rate code, e.g. `gst0`, `sr` for standard-rated) |

### `dim_location`

Single site today, future-proofed. Source: `systemsetup.locations[]`.

| Column | Notes |
|---|---|
| `location_id` (PK) | `given_id`, e.g. `"SG"` |
| `name` | from `print.header`, e.g. "Goji Health Pte. Ltd." |
| `address` | from `print.address` |
| `uen` | Singapore business identifier (e.g. `202601865N`) |
| `hci` | HCI code (Singapore healthcare licensing) |

### `dim_payer`

Who's settling the invoice. Singapore-typical types: `self_pay`, `corporate_insurance` (e.g. AIA, Great Eastern, Prudential), `chas` (Community Health Assist Scheme), `medisave_medishield`, `pioneer_or_merdeka`, `corporate_direct` (employer-paid). Sourced from Plato `corporate` records (currently empty per the probe) and Xero contacts once we add Xero.

| Column | Notes |
|---|---|
| `payer_id` (PK), `name`, `payer_type` | |

### `dim_account`

Xero chart of accounts.

| Column | Notes |
|---|---|
| `account_id` (PK), `code`, `name`, `type`, `class` (revenue/expense/asset/liability) | |

### `dim_queue_status`

From Plato `/queue/status/list`. Waiting / consulting / billed / completed / etc.

## Facts

### `fct_appointment`

Grain: one row per scheduled appointment.

| Column | Notes |
|---|---|
| `appointment_id` (PK) | |
| `date`, `start_ts`, `end_ts` | |
| `clinician_id`, `patient_id`, `service_id`, `location_id` | |
| `status` | booked / arrived / completed / cancelled / no_show |
| `booked_at` | the timestamp the booking was made (vs. the appointment date) |
| `duration_min` | end - start |
| `linked_invoice_id` | NULL until visit billed |

Used for: forward booking density, no-show rate, cancellation rate, clinician schedule view.

### `fct_clinician_capacity`

Grain: one row per clinician per day per slot window.

| Column | Notes |
|---|---|
| `date`, `clinician_id` | |
| `available_min` | open slot capacity |
| `blocked_min` | admin / leave / breaks |

Utilization metric = SUM(`fct_appointment.duration_min` where status in completed/arrived) / SUM(`fct_clinician_capacity.available_min`).

### `fct_invoice_line` - **THE BOOKING FACT**

Grain: one row per line item on an invoice (Plato invoice = queue entry).

| Column | Notes |
|---|---|
| `invoice_id`, `line_id` (composite PK) | |
| `invoice_date` | finalization date - the booking date |
| `booked_at` | invoice creation timestamp |
| `patient_id`, `clinician_id` (seller), `location_id`, `payer_id` | |
| `item_id` (-> `dim_service`) | |
| `qty`, `unit_price`, `discount`, `line_total`, `tax` | |
| `is_package_sale` | denormalised from `dim_service.is_package` for fast filters |
| `sessions_included` | qty * sessions_per_pack (for packs) OR qty (for single use) |
| `status` | draft / finalized / void |

**Used for:** cash bookings, sales by clinician (who sold what), package vs single-visit split, average sale value, top-selling items, AR pipeline (joined to `fct_payment`).

### `fct_service_delivered` - **THE REVENUE FACT**

Grain: one row per session actually rendered.

| Column | Notes |
|---|---|
| `delivery_id` (PK) | synthetic |
| `delivery_date`, `delivery_ts` | |
| `patient_id`, `clinician_id` (deliverer), `service_item_id`, `location_id` | |
| `source_invoice_line_id` | the original sale this draws from |
| `appointment_id` | the appointment that consumed the session (nullable) |
| `recognised_revenue` | `dim_service.per_session_value` of the source line |
| `delivery_method` | `single_use` (sold and consumed same day) or `package_burn` (drawn from outstanding pack) |

**Used for:** P&L revenue, recognised revenue per clinician (true earnings, not sales), revenue per visit, revenue mix by service.

How we build this: see "Deriving service delivery" below.

### `fct_package_balance` - **THE DEFERRED REVENUE FACT**

Grain: one row per patient per outstanding pack per day (snapshot).

| Column | Notes |
|---|---|
| `snapshot_date`, `patient_id`, `source_invoice_line_id` (composite PK) | |
| `item_id` | |
| `sessions_total`, `sessions_used`, `sessions_remaining` | |
| `deferred_revenue_remaining` | sessions_remaining * per_session_value |
| `days_since_purchase` | for ageing |
| `last_used_date` | for retention / win-back targeting |

**Used for:** balance-sheet deferred revenue, package burn-down dashboards, "patients about to expire pack" lists, pack expiry / breakage forecasting.

### `fct_payment`

Grain: one row per payment recorded against an invoice.

| Column | Notes |
|---|---|
| `payment_id` (PK) | |
| `payment_date` | |
| `invoice_id` | |
| `amount`, `method` (cash/card/transfer/platopay) | |
| `payer_id` | |

### `fct_bill` (Xero AP)

Grain: one row per supplier bill.

| Column | Notes |
|---|---|
| `bill_id` (PK), `contact_id`, `date`, `due_date`, `total`, `amount_due`, `status` | |

### `fct_gl` (Xero general ledger)

Grain: one row per ledger entry. For full P&L and balance-sheet reconciliation.

## Deriving service delivery (CONFIRMED FROM LIVE DATA 2026-05-23)

Plato records every session consumption as a new invoice line with `others.redeem_from` set to the original package's invoice id. We do NOT need snapshot diffing - each consumption is its own first-class record.

### The three line-item classifications

For every line in `invoice.item[]`:

| Classification | Detection rule | Booking $ | Recognised $ |
|---|---|---|---|
| **Redemption** (session consumed) | `item.others.redeem_from` is set | 0 | `sum(item.others.redeem_alloc[].value)` |
| **Package sale** (pack purchased) | `item.inventory == "package"` AND no `redeem_from` | `item.sub_total` (or `selling_price * qty`) | 0 (recognised later as sessions burn) |
| **Sale** (single-use product or service) | otherwise | `item.sub_total` | same as booking (recognised same day) |

### Extraction

- `fct_invoice_line` is populated from items classified as `package_sale` or `sale`.
- `fct_service_delivered` is populated from items classified as `redemption` (one row per `redeem_alloc` entry, so a 2-session redemption on one invoice yields 2 fact rows). The `clinician_id` for delivery comes from `invoice.doctor`; the `delivery_date` is `invoice.date`; the `source_invoice_line_id` comes from `redeem_alloc[].invoice` + `redeem_alloc[].item_id`. `recognised_revenue = redeem_alloc[].value`.
- `fct_service_delivered` is ALSO populated from `sale` items (single-use products and consults) - same row goes into both facts with the same date.

### `fct_package_balance`

Daily snapshot from `GET /{db}/reports/outstanding_packages?date={d}`. Field mapping:

| Plato field | BQ column |
|---|---|
| `patient_id` | `patient_id` |
| `item_id` | `source_invoice_line_id` (= the original sale's item) |
| `given_id` | `item_given_id` (cross-link to inventory) |
| `bought_date` | `purchased_date` |
| `last_activity` | `last_used_date` |
| `total_bought` | `sessions_total` |
| `total_left` | `sessions_remaining` |
| `total_spent` | `cash_collected` |
| **`pro_rata_left`** | **`deferred_revenue_remaining`** (Plato computes this for us - trust it) |
| `doctor` | `selling_clinician_id` |

`sessions_used = sessions_total - sessions_remaining` (derived).

This means **we don't compute per_session_value ourselves** - Plato's `pro_rata_left` is authoritative. The `redeem_alloc[].value` is also authoritative for individual delivery events.

## Key metrics this schema unlocks

| Metric | Source |
|---|---|
| Bookings $ (cash in) | `SUM(line_total)` from `fct_invoice_line` over period |
| Bookings count | `COUNT(invoice_id)` from `fct_invoice_line` |
| Recognised revenue $ | `SUM(recognised_revenue)` from `fct_service_delivered` |
| Deferred revenue (today) | `SUM(deferred_revenue_remaining)` from `fct_package_balance` WHERE snapshot_date = today |
| Cash vs revenue gap | bookings - recognised, by period |
| Pack utilisation rate | `sessions_used / sessions_total` per pack, aggregated |
| Patients with expiring packs | `fct_package_balance` filtered to days_since_purchase > 150 AND sessions_remaining > 0 |
| Clinician sales | bookings by clinician_id on `fct_invoice_line` |
| Clinician earnings (true) | recognised revenue by clinician_id on `fct_service_delivered` |
| Utilization % | delivered minutes / available minutes |
| AR aging | `fct_invoice` (rollup of lines) minus `fct_payment`, bucketed by days overdue |
| AP aging | `fct_bill` minus payments, bucketed |
| Forward booking density | `fct_appointment` count by date, for dates in next 7/14/30 days |
| New vs returning patient ratio | `dim_patient.first_visit_date` vs visit dates in `fct_service_delivered` |

## Assumptions verified against live API (2026-05-23)

| Assumption | Verified |
|---|---|
| Inventory items expose package info via `inventory == "package"` and `redeemable`/`redemptions` flags | YES |
| `/reports/outstanding_packages` returns per-patient-per-pack rows | YES, with `pro_rata_left` already computed |
| Invoice items link to inventory via `given_id` | YES |
| Clinician on each session is identifiable | YES, `invoice.doctor` = provider `given_id` |
| Session consumption is a first-class event in the API | YES - it's an invoice line with `others.redeem_from` set |

Net effect: the snapshot-diffing strategy in the original schema sketch is unnecessary. Every consumption event has a unique invoice line we can stream directly into `fct_service_delivered`.

## Open items deliberately deferred

- Xero org_id is single-tenant for now (one Xero org for the clinic, confirmed).
- Multi-location columns are present but unused.
- Payroll / clinician comp calculations not in v1; can be added as a `fct_clinician_comp` later.
- Marketing spend, Google Reviews not in v1.
