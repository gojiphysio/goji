# cash_book — Cash Book sheet → BigQuery

Cloud Run Job, every 2 hours. Snapshots the Cash Book Google Sheet into
`raw_cashbook.cash_book_raw`, which feeds the dashboard's P&L tab through
`stg.cash_book` → `marts.fct_cash_book` → `marts.fct_pnl_monthly`.

Keep typing in the sheet. Three columns tell the P&L what each row is:

| Column | Fill in | Meaning |
|---|---|---|
| **P&L line** | Every money-out row | Dropdown. Blank money-out rows count as Uncategorised costs, and the page warns about them. Leave blank on patient receipts |
| **Covers from** / **Covers to** | Only when payment and period differ | Payroll and CPF, utilities billed a month late, annual prepayments. Blank means the row's own month. The cost is spread evenly across these days |

Rows below EBITDA: **Capex**, **Deposit** (refundable, so never amortised),
**Financing** (shareholder loans) and **Non-operating**.

## What is stored

Numbers, dates, the P&L line, and a source type for credits. **Counterpart and
Purpose are never read into BigQuery**: the credit side holds patient names, and
`marts.dim_patient_contact` is the one sanctioned PII table. `sheet_row` traces
any figure back to the sheet.

## One-time setup

Do these before the SQL deploys, because `stg.cash_book` needs the table to exist.

1. **Sheet columns:** run the one-time Apps Script from the sheet
   (Extensions > Apps Script). It adds L:N, the dropdown and the backfill.
2. **Share the sheet** as Viewer with
   `ingestion-sa@goji-bi.iam.gserviceaccount.com`. There is no secret.
3. **Enable the API:**
   ```bash
   gcloud services enable sheets.googleapis.com --project=goji-bi
   ```
4. **Table:**
   ```bash
   bq --project_id=goji-bi --location=asia-southeast1 \
     query --use_legacy_sql=false < scripts/ingestion/cash_book/schema.sql
   ```
   No dataset grants are needed: `ingestion-sa@` (`dataEditor`) and `dashboard-sa@`
   (`dataViewer`) hold their roles at project level, as for `raw_marketing`.
5. **Repo var:** set `CASH_BOOK_SHEET_ID` in GitHub. The deploy step skips the job
   until it exists.
6. **Schedule**, off the hour so it stays clear of the Plato jobs:
   ```bash
   gcloud scheduler jobs create http cash-book-ingest-2h \
     --location=asia-southeast1 --schedule="17 */2 * * *" --time-zone="Asia/Singapore" \
     --uri="https://asia-southeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/goji-bi/jobs/cash-book-ingest:run" \
     --http-method=POST \
     --oauth-service-account-email="scheduler-sa@goji-bi.iam.gserviceaccount.com"
   ```

## Failure behaviour

- A missing required header (someone renamed **P&L line**) exits 3 and loads
  nothing, so the last good snapshot stays live.
- An empty read exits 3 for the same reason. It must not blank the P&L.
- A row with an unreadable date or amount is loaded with `parse_issue` set, and
  the page warns. A date typed without a year takes the year of the row above.

## Check it

```sql
SELECT FORMAT_DATE('%Y-%m', month) AS month, line, amount
FROM `goji-bi.marts.fct_pnl_monthly`
WHERE line = 'Payroll'
ORDER BY month
```

After the backfill, payroll by month should read: May 20,540, Jun 24,249,
Jul 25,917, Aug 26,045, Sep 26,524, Oct 28,973.
