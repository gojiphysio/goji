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
echo "==> Step 1/4: setting up the separate staff login"

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
echo "==> Step 2/4: building the behind-the-scenes data"
( cd "${HERE}/../sql" && ./deploy_all.sh )

# --- Step 3: permission to save follow-up actions ----------------------------
echo
echo "==> Step 3/4: allowing the dashboard to save follow-up actions"
if bq add-iam-policy-binding \
     --member="serviceAccount:${SA}" \
     --role="roles/bigquery.dataEditor" \
     "${PROJECT}:marts.patient_followup_events" >/dev/null 2>&1; then
  echo "    permission granted"
else
  echo "    (permission may already be set — continuing)"
fi

# --- Step 4: publish ---------------------------------------------------------
echo
echo "==> Step 4/4: publishing the dashboard (this puts the new screen online)"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --set-secrets=DASHBOARD_USER=dashboard-user:latest,DASHBOARD_PASS=dashboard-pass:latest,STAFF_USER=dashboard-staff-user:latest,STAFF_PASS=dashboard-staff-pass:latest,PLATO_API_KEY=plato-api-key:latest \
  --set-env-vars=GCP_PROJECT=${PROJECT},CACHE_TTL_SECONDS=300,PLATO_DB=gojihealth \
  --quiet

echo
echo "============================================================"
echo " Done — the Front Desk screen is live:"
echo "   https://dashboard.gojiphysio.com/admin"
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
