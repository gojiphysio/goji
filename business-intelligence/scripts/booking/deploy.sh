#!/usr/bin/env bash
#
# Deploy the goji-booking service — the website's direct-to-Plato booking backend
# at https://booking.gojiphysio.com. Own Cloud Run service (like goji-links),
# holds the Plato key server-side, writes appointments + funnel events.
#
# Runs as dashboard-sa (BigQuery dataEditor on marts.booking_funnel_events — add
# it to deploy_admin.sh's grant loop first). Secrets from Secret Manager:
#   plato-api-key        (required)  bearer token for Plato
#   gmail-app-password   (optional)  hello@ Google Workspace app password for the
#                                    admin notification email; skipped if absent
#
# Run from Google Cloud Shell:
#   bash business-intelligence/scripts/booking/deploy.sh
#
# Re-runnable. --max-instances=1 keeps the per-clinician in-process lock
# authoritative (do NOT raise it without moving the lock to a shared store).

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-booking}"
DOMAIN="${DOMAIN:-booking.gojiphysio.com}"
CORS_ORIGIN="${CORS_ORIGIN:-https://www.gojiphysio.com}"
SA="dashboard-sa@${PROJECT}.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

gcloud config set project "${PROJECT}" >/dev/null

# plato-api-key is required; gmail-app-password is optional (mailer degrades).
SECRETS="PLATO_API_KEY=plato-api-key:latest"
if gcloud secrets describe gmail-app-password >/dev/null 2>&1; then
  SECRETS="${SECRETS},GMAIL_APP_PASSWORD=gmail-app-password:latest"
  echo "==> mounting gmail-app-password (admin email enabled)"
else
  echo "==> gmail-app-password secret not found — admin email disabled (booking still works)"
fi

echo "==> Deploying ${SERVICE}"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --set-env-vars=GCP_PROJECT=${PROJECT},PLATO_DB=gojihealth,CORS_ORIGIN=${CORS_ORIGIN} \
  --set-secrets="${SECRETS}" \
  --max-instances=1 --min-instances=0 \
  --allow-unauthenticated \
  --quiet

echo "==> Mapping ${DOMAIN} -> ${SERVICE}"
gcloud components install beta --quiet || true
if gcloud beta run domain-mappings describe --domain="${DOMAIN}" \
     --platform=managed --region="${REGION}" --project="${PROJECT}" --quiet >/dev/null 2>&1; then
  echo "    domain mapping already exists"
else
  gcloud beta run domain-mappings create --service="${SERVICE}" \
    --domain="${DOMAIN}" --platform=managed --region="${REGION}" --project="${PROJECT}" --quiet
  echo "    >> Add DNS on gojiphysio.com:  booking  CNAME  ghs.googlehosted.com."
fi

echo "Done — booking API at https://${DOMAIN}/api/availability (+ /api/book, /api/track)"
