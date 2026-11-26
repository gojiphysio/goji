# goji-careers

The website's job-application backend: Cloud Run service `goji-careers` at
`https://careers-api.gojiphysio.com`, called by the careers form
(`marketing/website/src/components/careers/ApplicationForm.astro`).

What one submission does:

1. Accepts it only from `www.gojiphysio.com` (origin plus the `X-Goji-Careers`
   header), then runs the bot checks: a hidden honeypot field, a minimum fill
   time, and Cloudflare Turnstile.
2. Checks the role is still open, against the site's `/careers/vacancies.json`.
3. Validates the fields and the CV (PDF, DOC or DOCX, 10 MB max, real file
   signature). Google Drive virus-scans the upload itself.
4. Uploads the CV to the `Applications` folder in the **Goji Recruitment**
   Shared Drive as `<reference> - <name> - CV.<ext>`, then appends a row to the
   applicant tracker sheet. The reference is `GOJI-APP-<year>-NNNN`.
5. Emails hello@ (with links, never the CV), then sends the applicant a
   confirmation.

There is no endpoint that reads or lists applications. Reviewers use Drive and
Sheets with their own Goji accounts.

## Files

| File | What |
|---|---|
| `app.py` | The endpoint, bot checks, reference numbers, the tracker row |
| `validation.py` | Field rules and the CV check |
| `workspace.py` | The two Google calls: upload to Drive, append to Sheets |
| `mailer.py` | The internal email and the applicant confirmation |
| `vacancies.py` | Reads which roles are open from the website |
| `config.py` | Env vars, form option lists, tracker columns |
| `fakes.py`, `dev_server.py`, `test_careers.py` | Local and test only (not in the image) |

## Deploy

`.github/workflows/deploy-careers.yml`: pull requests run the tests; a merge to
`main` that touches `careers/` runs the tests and deploys. Nothing is deployed
by hand.

The service runs as `careers-sa@goji-bi.iam.gserviceaccount.com`, which has no
project roles. It can read two secrets (`gmail-app-password`,
`turnstile-secret`) and is a **Content manager** on the Goji Recruitment Shared
Drive. A service account has no Drive storage of its own, so the CV folder must
be inside a Shared Drive, not a My Drive folder shared with it.

## Test mode and going live

The workflow's `env:` block is the switch, so going live is a reviewed PR.

- **Now (test):** it points at the "Goji Recruitment (TEST)" folder and tracker,
  with `CAREERS_TEST_MODE: "1"`. Applicant confirmations go to
  `CAREERS_TEST_EMAIL` instead of the applicant; with no test address, no
  confirmation is sent at all.
- **Go live:**
  1. In the Shared Drive, make a copy of the TEST tracker (it has the header row
     and dropdowns), name it "Goji Recruitment — Applicant Tracker", clear its
     rows, and create an `Applications` folder beside it.
  2. In a PR, put their IDs in the workflow and set `CAREERS_TEST_MODE: "0"`.
  3. Set `PUBLIC_CAREERS_API=https://careers-api.gojiphysio.com` on the
     Cloudflare Pages production environment and rebuild the site. Until then
     the site shows "apply by email" instead of the form.

Before going live: a test submission per role and one expression of interest;
check the tracker row, the CV and both emails; management approves the
privacy notice and the retention periods (`RETENTION.md`).

## Website side

- `PUBLIC_CAREERS_API` turns the form on. The Turnstile widget uses the same
  site key as booking, and its hostname list must include every site the form
  runs on (`www.gojiphysio.com`, plus `goji.pages.dev` for preview testing).
- Testing on a Cloudflare Pages preview also needs that preview's origin added
  to `CORS_ORIGIN` in the workflow.

## Running locally

```bash
cd business-intelligence/scripts
uv run -q --with-requirements careers/requirements.txt --with pytest python -m pytest careers/ -q
uv run --with-requirements careers/requirements.txt python -m careers.dev_server
```

The dev server uses in-memory Drive/Sheets and prints emails instead of sending
them. Start the site with `PUBLIC_CAREERS_API=http://localhost:8090` (the
`website-careers-dev` entry in `.claude/launch.json`). `DEV_FAIL=upload` or
`DEV_FAIL=append` shows the storage error path. Use made-up data only.
