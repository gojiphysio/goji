# careers/: conventions

The job-application backend (`goji-careers`). Architecture, env, setup and the
testing matrix are in `README.md`; data retention in `RETENTION.md`. Rules:

- **Applicant data never leaves Drive/Sheets/email.** No CV content, names,
  emails or phone numbers in logs, error messages, analytics or the HTTP
  response. Log the reference and an error code only.
- **No sharing permissions, ever.** Nothing in this package may call the Drive
  `permissions` API. Access is the Shared Drive's membership.
- **No read or list endpoint.** The service only accepts submissions.
- **Tracker writes are RAW + INSERT_ROWS, and only the system columns.**
  `TRACKER_COLUMNS` in `config.py` is the order; the manual columns
  (Recruitment status, Assessed seniority level, Reviewer, Notes...) are
  written blank once and never touched again. Adding a column means adding it
  at the end of `TRACKER_COLUMNS` and of the live sheet in the same change.
- **Every write is idempotent on `idempotency_key`** (Drive `appProperties`).
  A new step in the flow gets its own done-flag on the application folder.
- **No auto-rejection or scoring.** Below-minimum days or years are recorded,
  never refused. No AI screening.
- **Test mode fails closed.** Don't add a path that emails the address on the
  form when `CAREERS_TEST_MODE` is on.
- **Vacancy truth is the website** (`marketing/website/src/lib/vacancies.ts`
  → `/careers/vacancies.json`). Don't hardcode roles here; the tests'
  `VACANCIES` fixture is the only copy.
- `--max-instances=1` keeps the reference lock and rate limits correct. Moving
  to more instances means moving both to a shared store first.
- **`deploy.sh` env delimiter is `|`.** `--set-env-vars` values hold `@`
  (emails) and `,` (CORS list), so neither can be the gcloud list delimiter.
- Tests run with `uv run -q --with-requirements careers/requirements.txt
  --with pytest python -m pytest careers/ -q` from `business-intelligence/scripts`.
