# careers/: conventions

The job-application backend (`goji-careers`). How it works, deploy and go-live
are in `README.md`; data retention in `RETENTION.md`. Rules:

- **Keep it small.** It is a form handler: validate, store the CV, append a
  row, send two emails. Don't add idempotency ledgers, per-role folder trees,
  deep file scanning or rate limiters without a real incident that needs one.
- **Applicant data never leaves Drive/Sheets/email.** No names, emails, phone
  numbers or CV content in logs, error messages or analytics. Log the
  reference and an error code only.
- **No sharing permissions and no read endpoint.** Access to applications is
  the Shared Drive's membership; the service only accepts submissions.
- **Tracker writes are RAW + INSERT_ROWS.** `TRACKER_COLUMNS` in `config.py`
  is the sheet's header order; a new column goes at the end of both. Rows are
  written by position, so removing or reordering a column means changing the
  live production and TEST trackers right after that deploy lands, or rows
  shift into the wrong columns.
- **One question set per form kind.** `validate_form` branches on the
  vacancy's `form` (`physio`, `pilates`, general); a kind's answers are blank
  on every other kind's row, and a role never stores answers it didn't ask
  (Pilates: no salary, notice period or AHPC). Option lists in `config.py`
  mirror `vacancies.ts`; values not on the list are dropped.
- **No auto-rejection or scoring.** Below-minimum days or years are recorded,
  never refused.
- **Test mode fails closed.** Never email the address on the form while
  `CAREERS_TEST_MODE` is on.
- **Deploys only from GitHub Actions** (`deploy-careers.yml`). The test /
  production switch is that workflow's `env:` block, so it changes by PR.
- **gcloud env-var lists use `^|^`.** Values hold `@` (emails) and `,` (CORS
  list), so neither can be the delimiter.
- `--max-instances=1` keeps the reference-number lock correct.
