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
confirmations, marketing operating-tool state, click-to-WhatsApp link clicks,
and provider-attribution alert dismissals; everything else stays read-only):

    for t in patient_followup_events lead_events marketing_ops_events link_click_events booking_funnel_events web_session_events mismatch_dismissal_events; do
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

(Once the GA4 export is linked, append `,GA4_DATASET=analytics_<propertyId>` to
`--set-env-vars` to light the Website-sessions card — see "GA4 website analytics".)

Then the front desk service from the same code (preserves its secrets,
incl. per-person staff logins):

    bash business-intelligence/scripts/dashboard/deploy_frontdesk.sh

The dashboard does not call Plato. The invoice-doctor mismatch alert reads
`marts.fct_invoice_doctor_mismatches` (a view over `stg.appointments`,
populated by `plato-appointments-ingest`), and the staff worklist reads patient
name + phone from `marts.dim_patient_contact` (populated by
`plato-patients-ingest`). Both come from BigQuery, so no `PLATO_API_KEY` is
mounted here.

## If a front-desk action can't save (HTTP 500 on dismiss/contacted/snooze/lead)

The dashboard SA must have **write** access to the relevant append-only table:
`marts.patient_followup_events` (retention worklist),
`marts.lead_events` (Leads pipeline),
`marts.marketing_ops_events` (founder Marketing tab operating tools),
`marts.link_click_events` (click-to-WhatsApp tracking), and
`marts.mismatch_dismissal_events` (provider-attribution alert dismissals).
`deploy_admin.sh` grants and verifies them all, but if you ever see a save
error, grant them directly:

    for t in patient_followup_events lead_events marketing_ops_events link_click_events booking_funnel_events web_session_events mismatch_dismissal_events; do
      bq add-iam-policy-binding \
        --member="serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com" \
        --role="roles/bigquery.dataEditor" \
        "goji-bi:marts.$t"
    done

(or in the Console: BigQuery → goji-bi → marts → <table> → Share → add the SA
as **BigQuery Data Editor**).

## Google Ads Data Transfer

The `goji-bi.google_ads` dataset is created and populated by the BigQuery Data Transfer
(source: Google Ads, daily at 08:00 SGT). The dataset lives in the **US multi-region** —
the dashboard queries it directly from Python (no cross-region view possible).

The dashboard SA needs read access on the dataset:

    bq add-iam-policy-binding \
      --member="serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com" \
      --role="roles/bigquery.dataViewer" \
      goji-bi:google_ads

(or in the Console: BigQuery → goji-bi → google_ads → Share → add the SA as
**BigQuery Data Viewer**).

## GA4 website analytics (Website-sessions card)

The "Website sessions" card reads the **free native GA4 → BigQuery export**. The
card and `fetch_web_sessions` ship inert: with `GA4_DATASET` unset they return
zeros, so nothing breaks before the export exists. To light it up — one-time:

1. **Create a GA4 property** for the website and note its **Measurement ID**
   (`G-XXXXXXX`) and numeric **property ID**.
2. **Add the tag to the site.** Set `PUBLIC_GA4_ID=G-XXXXXXX` in the Cloudflare
   Pages build env (Astro reads it in `BaseLayout.astro`; unset = no tag, so dev
   and the un-launched prototype stay untracked). **PDPA:** put a consent
   mechanism (banner or Google Consent Mode) in place before enabling in
   production — this is a Singapore healthcare site.
3. **Link GA4 → BigQuery** (GA4 Admin → Product links → BigQuery links → Link;
   pick the `goji-bi` project, daily export). GA4 creates a dataset
   `analytics_<propertyId>`. First data lands ~24–48h later.
4. **Grant the dashboard SA** read on that dataset (same as google_ads):

       bq add-iam-policy-binding \
         --member="serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com" \
         --role="roles/bigquery.dataViewer" \
         goji-bi:analytics_<propertyId>

5. **Tell the dashboard the dataset** via env vars on redeploy (see below):
   `GA4_DATASET=analytics_<propertyId>` (and `GA4_PROJECT` only if the export
   isn't in `goji-bi`). The GA4 export sits in the **US multi-region**; like
   `google_ads`, the dashboard queries it directly from Python.

**Channel attribution:** GA4 auto-captures `utm_*` on inbound links. Tag links
that point *into* the website (IG bio, GBP, ads, email) with
`utm_source=<slug>` matching the `LINK_SLUGS` taxonomy so sessions attribute to
the same channels the funnel uses. The `go.gojiphysio.com/<slug>` redirector
sends WhatsApp/Plato taps off-site (unaffected), but **`*-book` slugs land on our
own `/book`**, and the redirect now appends `?cid=<click_id>&src=<slug>` — the
first-party landing beacon records those on `marts.web_session_events`, closing
the click → session join without GA4.

**First-party arrival beacon (`marts.web_session_events`):** the Astro site's
`BaseLayout` posts a `session_start`/`page_view` to `goji-booking`
`POST /api/web-event` on every landing, capturing `utm_*`, `gclid`, `fbclid`,
`referrer`, `landing_path`, `cid` (go-link passthrough) against a first-party
`visitor_id` + the shared booking `session_id`. This is the deterministic
origin → surface → CTA → booked chain for the on-site booking journey; it's inert
until the site build sets `PUBLIC_BOOKING_API` (same PDPA-consent gate as GA4).

**Google Ads inflow:** turn on **auto-tagging** in Google Ads (Settings → Account
settings → Auto-tagging) so every ad click carries a `gclid`, and set ad **final
URLs** to the site with `utm_source=google&utm_medium=cpc&utm_campaign=<name>`
(use the same `<name>` as the campaign so it joins the `google_ads` transfer).
The beacon captures both; `utm_campaign` is the deterministic join key and
`gclid` the backup. Do the equivalent for Meta/IG paid (`fbclid` + utm). This is
what powers **cost-per-booking by campaign** on the Marketing tab.

**Google Ads conversion tracking (feeds Smart Bidding):** the booking flow fires a
`booking_confirmed` event on the confirmation step (valued at the service price),
via gtag. It reports a Google Ads conversion when the site build sets
`PUBLIC_GADS_ID` (`AW-…`) and `PUBLIC_GADS_BOOKING_LABEL` (the conversion-action
label) — both inert until set, same PDPA gate as GA4. Create the Website
conversion action in Google Ads to get those two values. The same event is
importable via GA4 if `PUBLIC_GA4_ID` is set instead. Full step-by-step:
**`marketing/ads/google-ads-playbook.md`** (also covers fixing the branded/junk
search-terms problem: campaign type, keyword match types, negatives, GBP).

## Plato online-booking attribution — spike verdict (2026-06)

**Question:** can a `?ref=<code>` we append to the Plato booking URL be traced
back through Plato so a tap → first-visit is linkable (the "click-id passthrough"
for the funnel's Plato-booking CTA)?

**Verdict: no, not via a URL param — leave Plato bookings "not linked yet".**
Desk review of the full Plato API docs (`business-intelligence/plato-api-docs/`)
found no field that a booking-URL param could land in or that we ingest:
- **Appointment** (`07-appointments.md`): `patient_id`, `title`, `description`,
  `starttime`, `endtime`, `color` (= calendar ID). `title`/`description` are
  patient-entered during booking, not URL-derived. No source/ref/UTM/custom field.
- **Online booking** endpoints (`onlineapptbooking/list`, `/slots`) expose only
  calendars and availability — nothing about a booking's origin.
- **Invoice**: the only `ref` (`09-invoice-queue.md`) is a *payment* reference on
  `/invoice/payment`, not a booking source.
- **Webhooks** (`06`) carry just `object_id`; `referred_by` is a pre-seeded
  *contact relationship* ("Online Booking - Instagram"), not a per-booking code.
- The booking page is Plato-hosted, so an appended query param is dropped.

**Only Plato-native source signal that IS ingestable:** the appointment `color`
(calendar ID, already pulled). Per-channel online-booking calendars would encode
source in `color` — but that fragments availability; not recommended for a small
clinic.

**To confirm empirically** (needs Plato + BQ access; expected to show nothing):
1. Open `<PLATO_BOOKING_URL>?ref=GOJITEST1` and complete one test booking.
2. `GET /{db}/appointment/{id}` and the draft `GET /{db}/invoice/{id}`; search
   every field for `GOJITEST1`. Or once ingested:
   `SELECT * FROM raw_plato.appointments_raw WHERE TO_JSON_STRING(payload) LIKE '%GOJITEST1%'`
   (and `invoices_raw`).
3. Appears → Plato preserves it, we can extract+join. Absent (expected) → dropped.

**Fallback today:** the manual "Online Booking - <source>" `referred_by` contacts
give a coarse Plato-booking source. The WhatsApp click-id passthrough (parked —
needs WhatsApp Cloud API + an inbox) is the path that would actually close the
loop for the primary CTA.

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
   - `SITE_BOOKING_URL` — the website booking form (defaults to
     `https://www.gojiphysio.com/book`). Enables the `*-book` slugs (the current
     booking CTA).
   - `PLATO_BOOKING_URL` — legacy Plato online-booking page URL. Enables the
     `*-plato` slugs (kept so old published links never dead-end).
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

Slugs are `<channel>-<destination>` — both explicit (`-wa` = WhatsApp, `-book` =
website `/book` form, `-plato` = legacy Plato booking), so nothing assumes a
default CTA and clicks attribute by channel. The **Book button now points to our
own `/book` form** (`-book`), not Plato. Publish each as
`https://go.gojiphysio.com/<slug>`:

| Where | WhatsApp button | Book button |
|---|---|---|
| Website (www.gojiphysio.com) | `…/web-wa` | `…/web-book` |
| `bio.site/gojiphysio` (IG/socials hub) | `…/bio-wa` | `…/bio-book` |
| Google Business Profile (later) | `…/gbp-wa` | `…/gbp-book` |
| Paid ads (later) | `…/ads-wa` | `…/ads-book` |
| QR codes (print / events / in-person) | `…/qr-wa` | `…/qr-book` |

`…/ig-wa` is available for any direct Instagram link; `…/wa` and `…/book` are
generic fallbacks. The legacy `…/*-plato` slugs still resolve (to
`PLATO_BOOKING_URL`) so previously-published booking links never dead-end, but new
surfaces should use `…/*-book`. **bio.site mailing-list button:** point it straight at the
signup page (untracked — nurture, not a primary CTA). **Instagram native
WhatsApp/email action buttons can't be wrapped** (not custom URLs); keep the IG
bio link pointing at bio.site so those clicks are tracked. Edit wording, change a
slug's destination, or add a channel in `LINK_SLUGS` in `app.py`. The Marketing
tab shows **Click-to-WhatsApp** and **Booking-link clicks** live, each split by
channel.

Front Desk portal (`frontdesk.gojiphysio.com`) — patient ops, no financials.
Three tabs — the worklists Plato doesn't track:

- **Leads** — inbound WhatsApp/Instagram/etc. inquiries tracked through the
  funnel (inquiry → booked → won, or lost), with a capture form and a funnel
  summary. "Won" = became a patient/customer, not "bought a package". Writes
  `marts.lead_events`. Replaces the founder Marketing tab's manual enquiry log.
- **Package alerts** (≤2 prepaid sessions left) — for renewal calls.
- **Follow-ups** — patients tiered by time since last visit
  (green ≤1wk / yellow >1wk / orange >2wk / red >4wk), excluding anyone with a
  future appointment booked or marked dismissed/snoozed. Front desk can mark
  **contacted / snooze / dismiss**; name + phone come from BigQuery
  (`dim_patient_contact`), plus a count of patients active in the last 12 months.

## Cost

- Cloud Run: scales to zero. With a few visits a day, well under $1/month.
  **Exception:** `goji-links` runs `--min-instances=1` (a warm container, a few
  $/month) — it's the public CTA redirector, and a cold start added several
  seconds to the first click after idle, long enough to lose the tap. Every other
  service still scales to zero.
- BQ: each page load is ~10 cheap queries (~few MB scanned each). Cached
  for 5 minutes so reloads don't multiply that. Should be free-tier-shaped.
- Secret Manager: 6 secret access calls per cold start. Free tier covers it.
