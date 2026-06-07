#!/usr/bin/env bash
#
# Stand up the Front Desk portal as its OWN Cloud Run service + subdomain:
#   https://frontdesk.gojiphysio.com
#
# Same container image as the financial dashboard, but launched with
# APP_MODE=frontdesk so it:
#   - serves the patient ops view at  /  (the subdomain is the front desk)
#   - returns 404 on every founder-only financial route (no financial data
#     is reachable here even with a founder credential)
#
# Founders' credential still works on this subdomain (skeleton key); it just
# lands on the same ops view as staff. Run from Google Cloud Shell:
#   bash business-intelligence/scripts/dashboard/deploy_frontdesk.sh
#
# Re-runnable. Does NOT touch the existing goji-dashboard service.

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-frontdesk}"
DOMAIN="${DOMAIN:-frontdesk.gojiphysio.com}"
SA="dashboard-sa@${PROJECT}.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo " Goji — publishing the Front Desk portal (separate service)"
echo " Project: ${PROJECT}   Region: ${REGION}   Service: ${SERVICE}"
echo "============================================================"
gcloud config set project "${PROJECT}" >/dev/null

# --- Sanity: the secrets the portal reuses must already exist ----------------
for s in dashboard-user dashboard-pass dashboard-staff-user dashboard-staff-pass; do
  if ! gcloud secrets describe "$s" --project="$PROJECT" >/dev/null 2>&1; then
    echo "ERROR: expected secret '$s' not found in ${PROJECT}."
    echo "       Run deploy_admin.sh first (it creates the staff secrets)."
    exit 1
  fi
done

# --- Per-person staff logins (optional) -------------------------------------
# The app reads extra staff accounts from STAFF_1_USER/PASS, STAFF_2_USER/PASS,
# ... Each maps to the 'staff' role. To give Claire/Cheryl/Kristy/etc. their
# own login, create secrets named  staff-<name>-user / staff-<name>-pass  and
# add them to STAFF_SECRETS below. The shared "frontdesk" login always works.
#
# Example to mint one (run once per person, then add to STAFF_SECRETS):
#   printf "claireng" | gcloud secrets create staff-claireng-user --data-file=- --project=goji-bi
#   python3 -c 'import secrets;print(secrets.token_urlsafe(12))' \
#     | tee /dev/tty | gcloud secrets create staff-claireng-pass --data-file=- --project=goji-bi
#
# Then set, e.g.:
#   STAFF_SECRETS="STAFF_1_USER=staff-claireng-user:latest,STAFF_1_PASS=staff-claireng-pass:latest"
STAFF_SECRETS="${STAFF_SECRETS:-}"

SECRETS="DASHBOARD_USER=dashboard-user:latest,DASHBOARD_PASS=dashboard-pass:latest"
SECRETS="${SECRETS},STAFF_USER=dashboard-staff-user:latest,STAFF_PASS=dashboard-staff-pass:latest"
if [ -n "${STAFF_SECRETS}" ]; then
  SECRETS="${SECRETS},${STAFF_SECRETS}"
fi

# --- Deploy the frontdesk service -------------------------------------------
echo
echo "==> Deploying ${SERVICE} (APP_MODE=frontdesk)"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --set-secrets="${SECRETS}" \
  --set-env-vars=GCP_PROJECT=${PROJECT},CACHE_TTL_SECONDS=300,APP_MODE=frontdesk \
  --allow-unauthenticated \
  --quiet

# --- Map the subdomain ------------------------------------------------------
echo
echo "==> Mapping ${DOMAIN} -> ${SERVICE}"
if gcloud run domain-mappings describe --domain="${DOMAIN}" \
     --region="${REGION}" --project="${PROJECT}" --quiet >/dev/null 2>&1; then
  echo "    domain mapping already exists"
else
  gcloud run domain-mappings create --service="${SERVICE}" \
    --domain="${DOMAIN}" --region="${REGION}" --project="${PROJECT}" --quiet
  echo
  echo "    >> Add this DNS record on the gojiphysio.com zone:"
  echo "         frontdesk  CNAME  ghs.googlehosted.com."
  echo "       (TLS cert auto-provisions once the CNAME resolves.)"
fi

echo
echo "============================================================"
echo " Done — Front Desk portal:"
echo "   https://${DOMAIN}"
echo " Founders sign in with their dashboard credential; staff with the"
echo " 'frontdesk' login (or their per-person login if you added one)."
echo "============================================================"
