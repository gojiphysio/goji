# goji-careers: job-application backend

The backend for the careers form on gojiphysio.com (`/careers/<role>/` and
`/careers/expression-of-interest/`). One endpoint, `POST /api/applications`,
which:

1. checks the request came from our site (Origin allowlist + the
   `X-Goji-Careers: 1` header, which forces a CORS preflight),
2. rate-limits (6 submissions per IP per hour, 3 per email per day) and runs
   the bot checks (honeypot `company_url`, minimum fill time, Turnstile),
3. confirms the role is open against the site's `/careers/vacancies.json`,
4. validates the fields and the CV (PDF/DOC/DOCX, 10MB, extension + MIME +
   file signature, active-content rejection),
5. allocates `GOJI-APP-YYYY-NNNN` and creates
   `Applications/<year>/<role folder>/<reference>/` in the recruitment Shared
   Drive, uploads `<reference>-CV.<ext>` and `<reference>-application.json`,
6. appends one row to **Goji Recruitment — Applicant Tracker** (RAW values,
   so nothing an applicant types is evaluated as a formula),
7. emails the clinic (links only, no attachment) and acknowledges the applicant.

There is no read or list endpoint. The service never creates sharing
permissions: who can see applications is decided by the Shared Drive's
membership. No AI screening, no scoring, no auto-rejection.

## Files

| File | What it holds |
|---|---|
| `app.py` | Flask app, the submission flow, CORS/origin check, rate limits, bot checks |
| `validation.py` | Field rules and the CV safety checks |
| `store.py` | Reference numbers, folder/file/tracker writes, idempotency |
| `workspace.py` | Thin Drive v3 / Sheets v4 REST client (google-auth) |
| `vacancies.py` | Reads the site's vacancy list (TTL cache, last good copy) |
| `mailer.py` | The two emails, wording from the brief |
| `config.py` | Every env var, the option lists, the tracker columns |
| `setup_workspace.py` | One-time creation of the folder tree and tracker |
| `dev_server.py` | Local harness: real app, fake Drive/Sheets, printed emails |
| `deploy.sh` | Manual Cloud Run deploy |

## Idempotency and partial failure

The browser sends an `idempotency_key` (UUID, one per page load). Every Drive
object the service writes carries it in `appProperties`, and the application
folder records which steps finished (`goji_tracker`, `goji_notified`,
`goji_acked`). A retry with the same key finds the folder, skips what is done,
finishes what is not, and returns the same reference. So a network drop after
upload never makes a second folder, a second tracker row or a second email.
If Drive or Sheets fails, the applicant sees "we couldn't send your
application" with the email fallback, and nothing is half-reported as success.

## Environment

| Variable | Default | Notes |
|---|---|---|
| `RECRUITMENT_APPLICATIONS_FOLDER_ID` | (required) | The `Applications` folder, printed by `setup_workspace` |
| `RECRUITMENT_TRACKER_SHEET_ID` | (required) | The tracker spreadsheet |
| `RECRUITMENT_TRACKER_TAB` | `Applicants` | |
| `GOOGLE_AUTH_MODE` | `service_account` | or `oauth` (see below) |
| `GOOGLE_OAUTH_CLIENT_JSON` | | secret `google-oauth-client`, oauth mode only |
| `CORS_ORIGIN` | `https://www.gojiphysio.com` | comma-separated |
| `VACANCIES_URL` | site `/careers/vacancies.json` | |
| `GMAIL_APP_PASSWORD` | | secret `gmail-app-password` |
| `CAREERS_ADMIN_EMAIL` | `hello@gojiphysio.com` | internal notification |
| `CAREERS_TEST_MODE` / `CAREERS_TEST_EMAIL` | off / empty | see Test mode |
| `TURNSTILE_SECRET` | | secret `turnstile-secret`; empty skips the check |
| `CAREERS_MIN_FILL_MS` | `8000` | faster submissions are treated as bots |
| `PRIVACY_NOTICE_VERSION` | `2026-11-draft` | written to every tracker row; bump when the notice changes |
| `RETENTION_REVIEW_DAYS` | `180` | provisional review date, see `RETENTION.md` |

Website side: Cloudflare Pages needs `PUBLIC_CAREERS_API` (the service URL).
Without it the form is not rendered and each page shows "Apply by email"
instead, so the site can ship before the backend is live. Turnstile reuses the
booking form's `PUBLIC_TURNSTILE_SITE_KEY`; the widget's hostname list must
include `www.gojiphysio.com` (it already does for booking).

## Google Workspace setup

**Preferred: Shared Drive + service account.**

1. In Google Workspace, create a Shared Drive called **Goji Recruitment**.
   Members: management and the people who review applications only. Check that
   link sharing outside the organisation is off for this drive.
2. Run `deploy.sh` once (it creates `careers-sa`), then add
   `careers-sa@goji-bi.iam.gserviceaccount.com` to the Shared Drive as
   **Content manager**.
3. Create the tree and tracker (from Cloud Shell, impersonating careers-sa or
   as a drive member with ADC):

   ```bash
   cd business-intelligence/scripts
   python3 -m careers.setup_workspace --parent <SHARED_DRIVE_ID> --test
   ```

   Run it again without `--test` for production. It prints the two IDs.
4. Re-run `deploy.sh` with those IDs.

**Fallback: hello@'s My Drive (`GOOGLE_AUTH_MODE=oauth`).** Only if a Shared
Drive isn't possible on the current Workspace plan. Create an OAuth client
(Desktop) in the goji-bi project, authorise it once as hello@ with the
`drive` and `spreadsheets` scopes, and store
`{"client_id","client_secret","refresh_token"}` in Secret Manager as
`google-oauth-client`. Never use a personal account.

## Test mode

`CAREERS_TEST_MODE=1` sends the applicant acknowledgement to
`CAREERS_TEST_EMAIL` instead of the address on the form. With no test address
it sends no acknowledgement at all (fails closed). `deploy.sh` defaults to test
mode on. Point it at the `(TEST)` folder and tracker while testing.

## Running locally

```bash
cd business-intelligence/scripts
uv run -q --with-requirements careers/requirements.txt --with pytest python -m pytest careers/ -q
uv run --with-requirements careers/requirements.txt --with pytest python -m careers.dev_server
```

Then start the site with `PUBLIC_CAREERS_API=http://localhost:8090` (the
`website-careers-dev` entry in `.claude/launch.json`). `DEV_FAIL=upload` (or
`append`, `create_folder`) makes the fake Drive/Sheets fail, to see the error paths.
`GET /dev/state` shows what the fake now holds. Use synthetic data only.

## Testing matrix

Automated (`pytest careers/`, 71 tests, CI: `careers-tests.yml`):

- valid full-time, part-time, either; part-time below the 3-day minimum is
  accepted with the days recorded (never auto-rejected)
- every required field missing; bad email (incl. header injection), phone,
  LinkedIn URL; options outside the lists dropped or refused
- general expression of interest skips the physio questions
- CV: PDF/DOC/DOCX accepted; wrong extension, double extension, signature or
  MIME mismatch, empty, over 10MB, PDF JavaScript/Launch/embedded files (also
  hex-escaped and inside compressed streams), DOCX macros/ActiveX/embeddings/
  remote templates, DOC macros: all refused
- closed role (409), unknown role, vacancy list unavailable (503 for roles; interest still accepted)
- an email failure still returns success and is not re-sent on retry
- origin and header checks, honeypot, too-fast fill, Turnstile, per-IP rate limit (retries not counted)
- retry with the same key: one folder, one CV, one row, one set of emails;
  retry after an upload or tracker failure completes the missing steps
- reference numbers continue from the tracker and Drive, per year
- test mode redirects or suppresses the acknowledgement
- formula-looking input is stored as text; logs carry no names or emails

Manual, before go-live (record the result in the PR):

- [ ] test-mode deploy against the `(TEST)` tree; one submission per role,
      one EOI, one part-time, one DOCX, one rejected file
- [ ] folder, CV, JSON and tracker row look right; links in the internal email
      open for a drive member and **not** for an outside account
- [ ] acknowledgement arrives at the test address only
- [ ] same submission retried (double-click, refresh during upload)
- [ ] keyboard-only and screen-reader pass on a phone
- [ ] management approves the privacy notice and retention periods

Only after every box is ticked: production IDs, `CAREERS_TEST_MODE=0`, set
`PUBLIC_CAREERS_API` on Cloudflare Pages, set the roles' `datePosted`.
