# goji-careers: job-application backend

Receives applications from the website's careers pages
(`/careers/<role>/` and `/careers/expression-of-interest/`), stores each one in
hello@gojiphysio.com's Google Drive with a row in the Applicant Tracker sheet,
and sends two emails: one to the clinic, one to the applicant.

**Status: built and unit-tested (80 tests), not yet operational.** Nothing has
been run against real Google, Gmail or Turnstile. It must go through the
one-time setup and the test matrix below, in test mode, before the website
points at it.

## How it fits together

```
browser form ──POST multipart──▶ careers-api.gojiphysio.com/api/apply   (Cloud Run, goji-careers)
                                   │ origin allowlist, rate limits, honeypot,
                                   │ time-to-fill, Turnstile, validation,
                                   │ CV checks (filecheck.py)
                                   ▼
                hello@'s Drive (OAuth refresh token, scope drive.file)
                  Goji Recruitment/
                    Applications/<year>/<role folder>/<GOJI-APP-YYYY-NNNN>/
                        <REF>-CV.pdf
                        <REF>-application-summary.json
                  Applicant Tracker (Google Sheet, one row per application)
                                   ▼
                Gmail SMTP as hello@: internal notification + applicant acknowledgement
```

- **Endpoints:** `POST /api/apply` and `GET /healthcheck`. There is no read,
  list or edit API: applications are only reachable in Drive and the Sheet by
  people hello@ shares them with.
- **Why an OAuth token, not a service account:** Goji has no Shared Drive, and
  a service account has no Drive storage of its own. `drive.file` means the
  service can see **only files it created**, nothing else in hello@'s Drive.
- **Vacancies** come from the website's
  `https://www.gojiphysio.com/careers/vacancies.json` (built from
  `marketing/website/src/content/careers/*.yaml`), cached 5 minutes. A closed
  role gets `410`, so a stale tab can't apply to it. `job_id=general` is the
  expression of interest and is always open.
- **Idempotent and resumable.** The browser sends a random `submission_id`.
  The server finds or creates one Drive folder per submission and records each
  step (`cv`, `summary`, `tracker`, `notified`, `acked`) in the folder's
  appProperties. A retry, or `admin reconcile`, resumes from the first undone
  step, so there are no duplicate rows, emails or references. The applicant
  sees success only after the CV, the summary and the tracker row are all
  stored. Emails are best-effort and retried by `reconcile`.
- **References** (`GOJI-APP-2026-0001`) come from a per-year counter in the
  root folder's appProperties, under a process lock. `--max-instances=1` and a
  single gunicorn worker keep that lock authoritative.
- **Tracker writes** use `valueInputOption=RAW` + `INSERT_ROWS`. A value like
  `=HYPERLINK(...)` is stored as text, never as a formula. The service only
  appends rows. It never rewrites one, so the manual columns (Status,
  Reviewer, Interview date, Notes, Next action) are never overwritten.

## Security and privacy controls

| Control | Where |
|---|---|
| Origin allowlist (www + extra preview origins) and `no-store` | `app.py` |
| 20 attempts per IP per hour, 3 applications per email per day | `app.py` |
| Honeypot `company_url`, minimum 5 s to fill, Turnstile (action `careers`) | `app.py` `_bot_reason` |
| Field validation and normalisation; CR/LF rejected in header-bound fields | `validation.py` |
| CV: ≤10 MB; PDF, DOC or DOCX by extension, declared MIME **and** file signature; rejects PDF JavaScript, launch actions and embedded files, Office macros, ActiveX, embedded OLE and remote templates; zip-bomb limits | `filecheck.py` |
| No NRIC, date of birth, photo or other sensitive fields collected | form + `validation.py` |
| Logs carry the reference and error codes only. They never carry names, contact details or CV text. | throughout |
| Analytics events carry the event name, `job_id` and `error_code` only | website `careers.ts` |
| No AI screening, scoring or ranking. People read every application. | by design |
| No link sharing anywhere in the folder tree | `admin check-access` |

**CV safety is structural, not antivirus.** The checks block the usual ways a
document carries active content, but no AV engine runs. Reviewers should
**open CVs in Drive's previewer**, not download them into Word. If the volume
grows, the next step is a ClamAV sidecar, which is free but adds about 1 GB of
image and memory.

## One-time setup

All of this is done once, by someone with owner access to the `goji-bi` GCP
project and signed in as hello@gojiphysio.com where noted.

1. **OAuth client.** Google Cloud console → `goji-bi` → APIs & Services:
   - enable the **Google Drive API** and **Google Sheets API**
   - OAuth consent screen: **Internal** (Workspace users only)
   - Credentials → Create OAuth client ID → **Desktop app**, named
     "goji-careers". Note the client ID and secret.
2. **Refresh token** (as hello@, on a laptop):
   ```bash
   cd business-intelligence/scripts
   CAREERS_GOOGLE_CLIENT_ID=… CAREERS_GOOGLE_CLIENT_SECRET=… python3 -m careers.admin authorize
   ```
   Sign in as **hello@gojiphysio.com** and approve. The command prints a
   refresh token. Do not paste it anywhere except the next step.
3. **Secrets** (Cloud Shell):
   ```bash
   printf %s "<client secret>" | gcloud secrets create careers-google-client-secret --data-file=-
   printf %s "<refresh token>" | gcloud secrets create careers-google-refresh-token --data-file=-
   ```
   `gmail-app-password` and `turnstile-secret` already exist (shared with
   goji-booking).
4. **Test folders and tracker first:**
   ```bash
   export CAREERS_GOOGLE_CLIENT_ID=… CAREERS_GOOGLE_CLIENT_SECRET=… CAREERS_GOOGLE_REFRESH_TOKEN=…
   python3 -m careers.admin setup --test
   ```
   This creates "Goji Recruitment (TEST)", its `Applications` folder and a test
   tracker. The tracker has a frozen header, a filter, a Status dropdown, date
   validation and a warning on header edits. The command prints the three IDs.
   Run it again later without `--test` for the live tree.
5. **Deploy in test mode** (first time from Cloud Shell; it also creates
   `careers-sa` and its secret grants):
   ```bash
   CAREERS_GOOGLE_CLIENT_ID=… CAREERS_DRIVE_ROOT_ID=… CAREERS_DRIVE_APPLICATIONS_ID=… \
   CAREERS_TRACKER_ID=… CAREERS_TEST_MODE=1 CAREERS_TEST_RECIPIENT=<staff inbox> \
   CAREERS_EXTRA_ORIGINS=<the PR's *.pages.dev origin> \
   bash business-intelligence/scripts/careers/deploy.sh
   ```
6. **DNS:** in Cloudflare, `careers-api` CNAME → `ghs.googlehosted.com`,
   **DNS only** (grey cloud), the same as the booking API.
7. **CI deploys:** set repo variables `CAREERS_GOOGLE_CLIENT_ID`,
   `CAREERS_DRIVE_ROOT_ID`, `CAREERS_DRIVE_APPLICATIONS_ID`,
   `CAREERS_TRACKER_ID`, `CAREERS_TEST_MODE`, `CAREERS_TEST_RECIPIENT`,
   `CAREERS_EXTRA_ORIGINS`. Also grant the deploy service account
   `roles/iam.serviceAccountUser` on `careers-sa`. Until `CAREERS_TRACKER_ID`
   is set, the workflow only runs tests.
8. **Website:** set `PUBLIC_CAREERS_API=https://careers-api.gojiphysio.com` in
   Cloudflare Pages (Preview first, then Production) and rebuild. Without it the
   form shows the email fallback in production, and a mock success in `astro dev`.

### Test mode

With `CAREERS_TEST_MODE=1`, **both** emails go to `CAREERS_TEST_RECIPIENT`
instead of the clinic and the applicant. If test mode is on and no recipient
is set, nothing is sent: it fails closed. Use the TEST folder and tracker, and
synthetic applicants only (`@example.com` addresses, made-up CVs). Never
use a real candidate's details for testing.

## Test matrix (before go-live, in test mode)

Unit tests (`80 passed`):

```bash
cd business-intelligence/scripts && uv run --python 3.12 --with flask==3.0.3 --with requests==2.32.3 --with pytest python -m pytest careers/ -q
```

Live checks still to run:

- [ ] Full-time application with a PDF CV → folder, CV, summary JSON, tracker row and both emails (to the test inbox)
- [ ] Part-time below the minimum days → stored, with "(below the stated minimum)" in the days column and the email (not rejected)
- [ ] DOCX and DOC CVs stored; `.exe` renamed to `.pdf` rejected; 11 MB file rejected; macro DOCX rejected
- [ ] Missing required fields → inline errors, nothing stored
- [ ] Expression of interest → filed under "General Expressions of Interest", worded as interest in both emails
- [ ] Double-click Submit / network retry → one row, one reference, one email each
- [ ] Applying to a role after setting it `closed` → 410 and the closed message
- [ ] Tracker: `=1+1` in a free-text field shows as text; Status dropdown works; a manual note survives the next application
- [ ] `admin check-access` reports no link sharing
- [ ] Turnstile, honeypot and the fill-time limit all refuse a bot-like submission
- [ ] Mobile (iOS Safari, Android Chrome): upload a CV from Files or Drive, then submit
- [ ] Keyboard-only and VoiceOver pass through the form and the error summary
- [ ] GA4 DebugView: `application_started`, `application_submitted`, `expression_of_interest_submitted` and `application_error` carry no name, email or phone

Then switch off test mode, run `setup` for the live tree, redeploy with the
live IDs, and submit one internal test application before announcing the role.

## Reviewing, retention and deletion

- **Reviewing:** open the Applicant Tracker, filter by Status, and follow the
  Drive folder link in each row. Update Status, Reviewer and Notes by hand.
  Share the tracker and folder only with named staff, never by link.
- **Retention:** 6 months after the role's decision, or 12 months where the
  applicant opted into the talent pool. The "Retention review date" column
  holds the date. Each month:
  ```bash
  python3 -m careers.admin retention
  ```
  This lists the references that are due. It changes nothing.
- **Deletion** (after review, or on an applicant's request):
  ```bash
  python3 -m careers.admin delete GOJI-APP-2026-0001 --confirm
  ```
  This moves the folder to hello@'s Drive Bin, which Drive empties after 30
  days. Then delete that row from the tracker by hand. The service never
  deletes rows itself, so the sheet stays under human control.
- **Hired candidates:** move their documents into the staff records and out of
  the recruitment tree. Recruitment retention no longer applies to them.
- **Part-stored applications** (for example, if Sheets was down):
  `python3 -m careers.admin reconcile --dry-run`, then without `--dry-run`.

## Files

`app.py` (Flask endpoints), `validation.py`, `filecheck.py`, `vacancies.py`,
`pipeline.py` (storage steps, reference IDs, reconcile), `google_store.py`
(Drive and Sheets REST over `requests`), `mailer.py`, `admin.py` (operator
CLI), `config.py`, `deploy.sh`, `Dockerfile`, `test_*.py` + `conftest.py`.
CI is `.github/workflows/deploy-careers.yml`.
