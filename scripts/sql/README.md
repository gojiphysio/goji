# BigQuery SQL views

All the SQL machinery that sits between the raw Plato landings and the dashboard. Read [`architecture/schema.md`](../../architecture/schema.md) first for the conceptual model; the files here are the executable version of that document.

## Layout

```
sql/
|-- stg/                          The staging layer. Reads raw_plato.*, dedupes, types.
|   |-- 01_invoices.sql           One row per invoice (latest version only).
|   |-- 02_invoice_items.sql      One row per line item, classified + booking/recognised amounts.
|   `-- 03_appointments.sql       One row per appointment (latest version), calendar→doctor resolved.
|
|-- marts/                        The reporting layer. Reads from stg.*. The dashboard reads from here.
|   |-- 10_fct_invoice_line.sql              The booking fact (sales + package sales).
|   |-- 20_fct_service_delivered.sql         The revenue fact (redemptions fanned + single-use sales).
|   `-- 30_fct_invoice_doctor_mismatches.sql Invoices whose doctor disagrees with the same-day calendar.
|
|-- deploy_all.sh                 Apply every view to BQ in dependency order.
`-- README.md                     This file.
```

Naming convention: filenames are prefixed with a numeric order (`01_`, `02_`, ...) so an alphabetical pass produces a valid dependency order. `marts/` numbers start at `10_` to keep stg/marts visually distinct.

## Dependencies

```
raw_plato.invoices_raw                      raw_plato.appointments_raw
        v                                              v
stg.invoices  ----v                            stg.appointments
                  stg.invoice_items                    |
                       v             v                 |
        marts.fct_invoice_line   marts.fct_service_delivered
                                                       |
        marts.fct_invoice_doctor_mismatches  <---------+
        (joins stg.invoices × stg.appointments)
```

Anything in `marts/` MUST read from `stg.*`, never from `raw_plato.*` directly. That's the whole point of the staging layer (decouples reporting from API shape changes).

## Deploying

After any .sql change:

```bash
cd scripts/sql/
./deploy_all.sh
```

Every view is `CREATE OR REPLACE`, so re-running is safe. The script runs `stg/` first then `marts/`, alphabetically inside each folder.

To deploy to a different project (e.g. a sandbox copy):

```bash
PROJECT=goji-bi-test ./deploy_all.sh
```

## Verifying after deploy

Three quick sanity queries. None of them should error.

**1. The classification split adds up.**

```sql
SELECT
  classification,
  COUNT(*) AS line_count,
  ROUND(SUM(booking_amount), 2)    AS bookings,
  ROUND(SUM(recognised_amount), 2) AS recognised
FROM `goji-bi.stg.invoice_items`
GROUP BY classification
ORDER BY classification;
```

Expectation: three rows (`sale`, `package_sale`, `redemption`). For `redemption` rows, `bookings` should be 0. For `package_sale` rows, `recognised` should be 0. For `sale` rows, `bookings == recognised` (both equal the line sub-total).

**2. Per-clinician bookings vs recognised (the first dashboard question).**

```sql
WITH bookings AS (
  SELECT clinician_id, SUM(booking_amount) AS bookings
  FROM `goji-bi.marts.fct_invoice_line`
  WHERE invoice_date >= CURRENT_DATE() - 30
  GROUP BY clinician_id
),
revenue AS (
  SELECT clinician_id, SUM(recognised_revenue) AS recognised
  FROM `goji-bi.marts.fct_service_delivered`
  WHERE delivery_date >= CURRENT_DATE() - 30
  GROUP BY clinician_id
)
SELECT
  COALESCE(b.clinician_id, r.clinician_id) AS clinician_id,
  ROUND(COALESCE(b.bookings,   0), 2) AS bookings_30d,
  ROUND(COALESCE(r.recognised, 0), 2) AS recognised_30d,
  ROUND(COALESCE(b.bookings, 0) - COALESCE(r.recognised, 0), 2) AS booking_recognition_gap
FROM bookings b
FULL OUTER JOIN revenue r USING (clinician_id)
ORDER BY bookings_30d DESC;
```

Expectation: a row per active clinician (`PCN`, `PCL`, `PKN`). Bookings > recognised when packs are being sold faster than they're being delivered; the reverse when burn is catching up.

**3. Redemption fan-out works.**

```sql
SELECT
  invoice_id,
  COUNT(*) AS delivery_rows
FROM `goji-bi.marts.fct_service_delivered`
WHERE delivery_method = 'package_burn'
GROUP BY invoice_id
HAVING COUNT(*) > 1
ORDER BY delivery_rows DESC
LIMIT 5;
```

Expectation: invoices where a single line redeemed multiple sessions (e.g. two consults billed against a 10-pack on one visit) appear with `delivery_rows > 1`. Zero rows is also fine if no multi-session redemptions exist yet.

## When a view changes

1. Edit the .sql file.
2. Run `./deploy_all.sh`.
3. Re-run the relevant sanity query above.
4. The dashboard picks up the change on its next cache refresh (≤5 min, or POST `/refresh`).

Adding a new view: drop a new .sql file in `stg/` or `marts/` and bump the numeric prefix to sort it correctly relative to dependencies. No code wiring needed.
