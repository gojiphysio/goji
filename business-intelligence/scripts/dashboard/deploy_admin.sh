#!/usr/bin/env bash
#
# One-shot setup for the staff admin dashboard (the "Front Desk" / patient
# retention screen). Safe to run more than once.
#
# It does the three "go-live" steps for you:
#   1. Creates the separate staff login (username + a strong random password).
#   2. Builds the behind-the-scenes data it reads (the retention view + the
#      follow-up table where "contacted / snooze / dismiss" actions are saved).
#   3. Gives the dashboard the minimal permission to save those actions, then
#      publishes the updated dashboard so the new screen goes live.
#
# Run it from Google Cloud Shell:
#   bash business-intelligence/scripts/dashboard/deploy_admin.sh
#
# Nothing here touches the existing financial dashboard — that keeps working
# exactly as before.

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-dashboard}"
SA="dashboard-sa@${PROJECT}.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo " Goji — publishing the staff Front Desk dashboard"
echo " Project: ${PROJECT}   Region: ${REGION}"
echo "============================================================"
gcloud config set project "${PROJECT}" >/dev/null

# --- Step 1: the staff login -------------------------------------------------
echo
echo "==> Step 1/5: setting up the separate staff login"

STAFF_USER_NAME="frontdesk"
STAFF_PW=""

if gcloud secrets describe dashboard-staff-user --project="$PROJECT" >/dev/null 2>&1; then
  echo "    staff username already exists — leaving it as-is"
else
  printf "%s" "$STAFF_USER_NAME" | \
    gcloud secrets create dashboard-staff-user --data-file=- --project="$PROJECT" >/dev/null
  echo "    created staff username: ${STAFF_USER_NAME}"
fi

if gcloud secrets describe dashboard-staff-pass --project="$PROJECT" >/dev/null 2>&1; then
  echo "    staff password already set — leaving it unchanged"
else
  STAFF_PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
  printf "%s" "$STAFF_PW" | \
    gcloud secrets create dashboard-staff-pass --data-file=- --project="$PROJECT" >/dev/null
  echo "    created a strong staff password (shown at the end)"
fi

# Sanity check: the Plato key the new screen reuses must already exist.
if ! gcloud secrets describe plato-api-key --project="$PROJECT" >/dev/null 2>&1; then
  echo "ERROR: expected secret 'plato-api-key' was not found in ${PROJECT}."
  echo "       This is the key your data jobs already use. Stop here and ask"
  echo "       whoever set up your current dashboard — something's off."
  exit 1
fi

# --- Step 2: the data --------------------------------------------------------
echo
echo "==> Step 2/5: building the behind-the-scenes data"
( cd "${HERE}/../sql" && ./deploy_all.sh )

# --- Step 3: permission to save front-desk actions ---------------------------
# The dashboard writes several append-only event logs: follow-up actions
# (retention worklist), inbound leads (the Leads pipeline), click-to-WhatsApp
# link clicks, website booking-funnel + landing beacons, and provider-attribution
# alert dismissals. Each needs a table-level dataEditor grant on the SA — we keep
# it table-level, not dataset-wide, for least privilege.
echo
echo "==> Step 3/5: allowing the dashboard to save front-desk actions"
grant_editor() {
  local table="$1" label="$2"
  bq add-iam-policy-binding \
    --member="serviceAccount:${SA}" \
    --role="roles/bigquery.dataEditor" \
    "${PROJECT}:marts.${table}" >/dev/null 2>&1 || true
  # Verify the binding actually took. Its absence is exactly what causes
  # "Could not save (HTTP 500)" when the front desk takes an action, so we
  # stop loudly rather than let that ship silently.
  if bq get-iam-policy "${PROJECT}:marts.${table}" 2>/dev/null | grep -q "${SA}"; then
    echo "    write permission confirmed (${label})"
  else
    echo
    echo "    !! Could NOT give the dashboard permission to save ${label} — saving WILL fail."
    echo "       Fix it once in the Cloud Console (about a minute):"
    echo "         BigQuery  >  ${PROJECT}  >  marts  >  ${table}"
    echo "         > Share  >  Add principal"
    echo "         principal:  ${SA}"
    echo "         role:       BigQuery Data Editor    > Save"
    echo "       Then re-run this script. Stopping here so this isn't missed."
    exit 1
  fi
}
grant_editor patient_followup_events    "follow-up actions"
grant_editor lead_events                "inbound leads"
grant_editor link_click_events          "click-to-WhatsApp tracking"
grant_editor booking_funnel_events      "website booking-funnel tracking (goji-booking)"
grant_editor web_session_events         "website landing/attribution beacon (goji-booking)"
grant_editor mismatch_dismissal_events  "provider-attribution alert dismissals"

# --- Step 4: refresh patient names ------------------------------------------
# Names + phones now come from BigQuery (marts.dim_patient_contact), filled by
# the patients-ingest job. Redeploy it with the new code and run it once so the
# worklist shows full names right away. Non-fatal: if it can't run now, the
# nightly job fills names later — so we warn and carry on to publishing.
echo
echo "==> Step 4/5: refreshing patient names (one-off; can take a few minutes)"
INGEST_DIR="${HERE}/../ingestion/plato_patients"
if ( cd "${INGEST_DIR}" && gcloud run jobs deploy plato-patients-ingest \
       --source . --region="${REGION}" --project="${PROJECT}" --quiet ); then
  echo "    names job updated — running it once now…"
  gcloud run jobs execute plato-patients-ingest \
    --region="${REGION}" --project="${PROJECT}" --wait \
    || echo "    (couldn't run it now — tonight's 9pm run will fill the names)"
else
  echo "    (couldn't update the names job now — tonight's 9pm run will fill the names)"
fi

# --- Step 5: publish ---------------------------------------------------------
echo
echo "==> Step 5/5: publishing the dashboard (this puts the new screen online)"
# The dashboard no longer calls Plato directly — names come from BigQuery — so
# PLATO_API_KEY is intentionally not mounted here anymore.
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --set-secrets=DASHBOARD_USER=dashboard-user:latest,DASHBOARD_PASS=dashboard-pass:latest,STAFF_USER=dashboard-staff-user:latest,STAFF_PASS=dashboard-staff-pass:latest \
  --set-env-vars=GCP_PROJECT=${PROJECT},CACHE_TTL_SECONDS=300 \
  --allow-unauthenticated \
  --quiet

echo
echo "============================================================"
echo " Done — shared setup complete (staff login, data, write grants)."
echo
echo " The Front Desk screen lives on its OWN subdomain now, not on the"
echo " dashboard. Publish/refresh it with:"
echo "   bash business-intelligence/scripts/dashboard/deploy_frontdesk.sh"
echo " Then it's live at:"
echo "   https://frontdesk.gojiphysio.com"
echo
echo " Staff sign in with:"
echo "   username: ${STAFF_USER_NAME}"
if [ -n "$STAFF_PW" ]; then
  echo "   password: ${STAFF_PW}"
  echo
  echo " >> Save this password somewhere safe — it is NOT shown again. <<"
else
  echo "   password: (unchanged — it was already set on a previous run)"
fi
echo "============================================================"
