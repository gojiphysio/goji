# Dashboard deploy notes

Live:

- Founders / finance: <https://dashboard.gojiphysio.com>  (`APP_MODE=dashboard`)
- Whole team / front desk: <https://frontdesk.gojiphysio.com>  (`APP_MODE=frontdesk`)

Cloud Run URL: <https://goji-dashboard-277737358846.asia-southeast1.run.app>

Both subdomains run the **same container image** (`app.py`), gated by HTTP Basic
Auth, querying BigQuery on each page load with a 5-minute in-process cache. The
only difference is the `APP_MODE` env var, which selects the routes and audience.

## Two subdomains, one codebase

There are exactly two ways in, and each subdomain 404s the other's routes:

Each subdomain serves its own portal at `/` — the subdomain *is* the audience.

- **`dashboard.*`** (`APP_MODE=dashboard`, default) — the financial dashboard
  only (`/`, `/api/data`, P&L, commission), founder-only. The patient ops portal
  is **not** served here: the legacy `/admin` and the `/api/frontdesk/*` routes
  return **404**.
- **`frontdesk.*`** (`APP_MODE=frontdesk`) — the patient ops portal at `/` (no
  redundant `/frontdesk` path; the legacy `/admin` 301-redirects to `/`). Every
  founder-only financial route returns **404**, so no financial data is reachable
  here even with a founder credential. Used by reception **and** clinicians
  (Plato covers clinician schedule/performance, so there is no separate clinician
  portal).

## Roles

- **Founders** (`DASHBOARD_USER`/`DASHBOARD_PASS`) — skeleton key: full access on
  `dashboard.*`, and on `frontdesk.*` they land on the ops view.
- **Staff** — one or more credential pairs, all mapping to the `staff` role:
  - legacy single pair `STAFF_USER`/`STAFF_PASS` (the shared `frontdesk` login)
  - per-person extras `STAFF_1_USER`/`STAFF_1_PASS`, `STAFF_2_USER`/`STAFF_2_PASS`,
    … (username format `firstnamelastname`, e.g. `claireng`). Add as many as
    there are team members.
  A staff credential returns 401/404 on every financial route. Role gating lives
  in `resolve_role(...)` / `require_roles(...)` in `app.py`.

## Stand up the front desk subdomain

One command from Cloud Shell creates the `goji-frontdesk` service + domain mapping:

    bash business-intelligence/scripts/dashboard/deploy_frontdesk.sh

It reuses the existing secrets. To give people their own logins, mint per-person
secrets and pass them in (see the comments at the top of the script):

    STAFF_SECRETS="STAFF_1_USER=staff-claireng-user:latest,STAFF_1_PASS=staff-claireng-pass:latest" \
      bash business-intelligence/scripts/dashboard/deploy_frontdesk.sh

## Architecture

- **Cloud Run service** `goji-dashboard` in `asia-southeast1`.
- Runs as `dashboard-sa@goji-bi.iam.gserviceaccount.com` — read-only on BQ,
  **plus write on the single follow-up table** (see below).
- Reads `DASHBOARD_USER`/`DASHBOARD_PASS` and `STAFF_USER`/`STAFF_PASS` from
  Secret Manager at boot (`dashboard-user`, `dashboard-pass`, `dashboard-staff-user`,
  `dashboard-staff-pass`).
- The dashboard does **not** call Plato. The admin worklist reads patient name +
  phone from `marts.dim_patient_contact`, written nightly by the
  `plato-patients-ingest` job (the one place that holds patient PII; the
  financial dashboard never reads it).
- Container: `python:3.12-slim` + Flask + gunicorn + google-cloud-bigquery.
- One revision keeps 0..3 instances; concurrency 20; memory 512Mi.

## Files

- `app.py` — Flask app, BQ queries, role-based basic-auth, cache.
- `template.html` — founder dashboard markup. Contains `__DATA_PLACEHOLDER__`.
- `admin.html` — staff admin (retention worklist) markup.
- `Dockerfile`, `requirements.txt`, `.dockerignore` — Cloud Run build inputs.

## One-time setup for the admin section

Create the staff secrets:

    python3 -c "import secrets; print(secrets.token_urlsafe(18))" | \
      gcloud secrets create dashboard-staff-pass --data-file=- --project=goji-bi
    printf "frontdesk" | \
      gcloud secrets create dashboard-staff-user --data-file=- --project=goji-bi

Deploy the follow-up state objects (idempotent; the events table is
`CREATE TABLE IF NOT EXISTS`, so it won't clobber data on re-run):

    cd ../sql && ./deploy_all.sh

Grant the dashboard SA write on **only** the append-only event tables (so it
can append "contacted/snoozed/dismissed" follow-up events, appointment
confirmations, marketing operating-tool state, and click-to-WhatsApp link
clicks; everything else stays read-only):

    for t in patient_followup_events appt_confirmation_events marketing_ops_events link_click_events; do
      bq add-iam-policy-binding \
        --member="serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com" \
        --role="roles/bigquery.dataEditor" \
        "goji-bi:marts.$t"
    done

## Read the password

    gcloud secrets versions access latest --secret=dashboard-pass --project=goji-bi
    gcloud secrets versions access latest --secret=dashboard-user --project=goji-bi

## Rotate the password

    NEW_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(18))")
    printf "%s" "$NEW_PASS" | gcloud secrets versions add dashboard-pass --data-file=- --project=goji-bi
    gcloud run services update goji-dashboard --region=asia-southeast1 --project=goji-bi \
      --update-secrets=DASHBOARD_PASS=dashboard-pass:latest
    echo "New password: $NEW_PASS"

(Cloud Run resolves `:latest` at boot; the update bounces a new revision.)

## Redeploy after a code change

Normally you don't — pushing to `main` auto-deploys **both** services
(`goji-dashboard` and `goji-frontdesk`) via `.github/workflows/deploy-dashboard.yml`.
To deploy by hand (e.g. from a branch), do both services from the same code:

    cd scripts/dashboard
    gcloud run deploy goji-dashboard \
      --project=goji-bi --region=asia-southeast1 --source=. \
      --service-account=dashboard-sa@goji-bi.iam.gserviceaccount.com \
      --set-secrets=DASHBOARD_USER=dashboard-user:latest,DASHBOARD_PASS=dashboard-pass:latest,STAFF_USER=dashboard-staff-user:latest,STAFF_PASS=dashboard-staff-pass:latest \
      --set-env-vars=GCP_PROJECT=goji-bi,CACHE_TTL_SECONDS=300,APP_MODE=dashboard \
      --quiet

Then the front desk service from the same code (preserves its secrets,
incl. per-person staff logins):

    bash business-intelligence/scripts/dashboard/deploy_frontdesk.sh

The dashboard does not call Plato. The invoice-doctor mismatch alert reads
`marts.fct_invoice_doctor_mismatches` (a view over `stg.appointments`,
populated by `plato-appointments-ingest`), and the staff worklist reads patient
name + phone from `marts.dim_patient_contact` (populated by
`plato-patients-ingest`). Both come from BigQuery, so no `PLATO_API_KEY` is
mounted here.

## If a front-desk action can't save (HTTP 500 on dismiss/contacted/snooze/confirm)

The dashboard SA must have **write** access to the relevant append-only table:
`marts.patient_followup_events` (retention worklist),
`marts.appt_confirmation_events` (call-list confirmations),
`marts.marketing_ops_events` (founder Marketing tab operating tools), and
`marts.link_click_events` (click-to-WhatsApp tracking).
`deploy_admin.sh` grants and verifies all four, but if you ever see a save
error, grant them directly:

    for t in patient_followup_events appt_confirmation_events marketing_ops_events link_click_events; do
      bq add-iam-policy-binding \
        --member="serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com" \
        --role="roles/bigquery.dataEditor" \
        "goji-bi:marts.$t"
    done

(or in the Console: BigQuery → goji-bi → marts → <table> → Share → add the SA
as **BigQuery Data Editor**).

## Force a cache refresh without redeploying

    curl -X POST -u "$USER:$PASS" https://dashboard.gojiphysio.com/refresh

## Tail logs

    gcloud logging tail 'resource.type=cloud_run_revision AND resource.labels.service_name=goji-dashboard' --project=goji-bi

## Custom domain

`dashboard.gojiphysio.com` is live: a `dashboard` CNAME → `ghs.googlehosted.com.`
on the `gojiphysio.com` zone, with Google's auto-provisioned TLS cert. The
domain mapping lives in Cloud Run.

Verify / inspect:

    dig +short dashboard.gojiphysio.com         # CNAME → ghs.googlehosted.com.
    curl -I https://dashboard.gojiphysio.com/   # 401 (auth required)
    gcloud beta run domain-mappings describe \
      --domain=dashboard.gojiphysio.com --platform=managed \
      --region=asia-southeast1 --project=goji-bi

## What this dashboard shows

Founder dashboard — four pages, all live from BQ:

- **Overview** — KPIs, daily/weekly/monthly trends, per-clinician table,
  discount summary, treatment-mix donuts, cohort table, deferred revenue,
  patient demographics, referral analytics, and the invoice-doctor mismatch alert.
- **P&L** — Singapore-style P&L with revenue/bookings toggle, period selector,
  and XLSX export.
- **Commission** — per-clinician commission calculator over real appointment data.
- **Marketing** — campaign view for the 90-day plan: north-star KPIs (visits,
  active patients, bookings) and patient acquisition live from BQ; channel
  leading indicators (Instagram, GBP, website, paid) as **WIP placeholders**
  until those integrations land; a delivery-lane mix + ICP/clinical-focus
  readout; referral-source breakdown (with a note that Plato attribution is
  coarse); plus light operating tools — a weekly-rhythm checklist, the 12-week
  content calendar, a partnership pipeline, and an enquiry log. The operating
  tools persist to `marts.marketing_ops_events` (append-only, latest wins; same
  pattern as the follow-up log). The **Click-to-WhatsApp** card is live from
  `marts.link_click_events` (see below).

### Trackable CTA links (`go.gojiphysio.com/<slug>`)

Every customer CTA routes through a public redirector that logs the click then
302s to its destination — **WhatsApp** (the primary CTA) or **Plato booking**
(socials like `bio.site/gojiphysio` offer both). It runs as its **own** Cloud Run
service `goji-links` (`APP_MODE=links`) on `go.gojiphysio.com` — a short, on-brand
domain that serves *only* the redirects, keeping the internal
`dashboard.gojiphysio.com` tool out of public view. Each hit logs a row to
`marts.link_click_events` (streaming insert, off-thread); WhatsApp slugs add a
channel-specific prefilled message that also seeds the enquiry-log source.
Slugs/kinds/messages are defined in `LINK_SLUGS` in `app.py`. (The dashboard
service also keeps `GET /r/<slug>` working internally, but the published links are
`go.gojiphysio.com/<slug>`.)

**Setup — all via GitHub Actions, no Cloud Shell:**

1. Set **GitHub Actions repository variables** (Settings → Secrets and variables
   → Actions → **Variables**):
   - `WHATSAPP_NUMBER` — WhatsApp business number, E.164 digits, no `+`
     (e.g. `6580000000`). Enables the WhatsApp slugs.
   - `PLATO_BOOKING_URL` — your Plato online-booking page URL. Enables the `book`
     slug.
   - `WHATSAPP_FALLBACK_URL` — optional; where the bare root and any unconfigured
     slug go (defaults to `https://www.gojiphysio.com`). Until a target is set,
     links fall back here so they never dead-end.
2. Push to `main` (e.g. merge this PR). The deploy workflow **creates** the
   `goji-links` service and the `go.gojiphysio.com` domain mapping on first run
   (and keeps them in sync after), then prints the one DNS record to add.
3. **One-time DNS** (the only manual step — it's on your DNS host, not GCP): add
   `go  CNAME  ghs.googlehosted.com.` on the `gojiphysio.com` zone. TLS
   auto-provisions once it resolves.

`deploy_links.sh` does the same standup from Cloud Shell if you ever need a manual
fallback, but the workflow is the primary path.

Slugs are `<channel>-<destination>` — both explicit (`-wa` = WhatsApp, `-plato` =
Plato booking), so nothing assumes a default CTA and clicks attribute by channel.
Publish each as `https://go.gojiphysio.com/<slug>`:

| Where | WhatsApp button | Book button |
|---|---|---|
| Website (www.gojiphysio.com) | `…/web-wa` | `…/web-plato` |
| `bio.site/gojiphysio` (IG/socials hub) | `…/bio-wa` | `…/bio-plato` |
| Google Business Profile (later) | `…/gbp-wa` | `…/gbp-plato` |
| Paid ads (later) | `…/ads-wa` | `…/ads-plato` |
| QR codes (print / events / in-person) | `…/qr-wa` | `…/qr-plato` |

`…/ig-wa` is available for any direct Instagram link; `…/wa` and `…/plato` are
generic fallbacks. **bio.site mailing-list button:** point it straight at the
signup page (untracked — nurture, not a primary CTA). **Instagram native
WhatsApp/email action buttons can't be wrapped** (not custom URLs); keep the IG
bio link pointing at bio.site so those clicks are tracked. Edit wording, change a
slug's destination, or add a channel in `LINK_SLUGS` in `app.py`. The Marketing
tab shows **Click-to-WhatsApp** and **Booking-link clicks** live, each split by
channel.

Front Desk portal (`frontdesk.gojiphysio.com`) — patient ops, no financials.
Four tabs: **Today** (schedule), **Call list** (unconfirmed appts),
**Package alerts** (≤2 sessions left), and:

- **Retention worklist** — patients tiered by time since last visit
  (green ≤1wk / yellow >1wk / orange >2wk / red >4wk), excluding anyone with a
  future appointment booked or marked dismissed/snoozed. Front desk can mark
  **contacted / snooze / dismiss**; name + phone come from BigQuery
  (`dim_patient_contact`), plus a count of patients active in the last 12 months.

## Cost

- Cloud Run: scales to zero. With a few visits a day, well under $1/month.
- BQ: each page load is ~10 cheap queries (~few MB scanned each). Cached
  for 5 minutes so reloads don't multiply that. Should be free-tier-shaped.
- Secret Manager: 6 secret access calls per cold start. Free tier covers it.
