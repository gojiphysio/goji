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
# PRIMARY PATH: pushes to `main` that touch scripts/booking/** auto-deploy via
# .github/workflows/deploy-booking.yml (tests gate it; WIF auth, no key). This
# script is the manual fallback (or first-time standup) — run from Cloud Shell:
#   bash business-intelligence/scripts/booking/deploy.sh
# Keep the two in sync: the workflow mirrors the gcloud args below.
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

# Both secrets are mounted unconditionally — plato-api-key (Plato) and
# gmail-app-password (confirmation/admin emails). Both exist in Secret Manager;
# the runtime SA (dashboard-sa) has secretAccessor. Do NOT gate the gmail mount on
# `gcloud secrets describe`: under CI the deploy SA can't read Secret Manager, so
# that check dropped the mount and disabled emails. Keep this matching the CI
# workflow (.github/workflows/deploy-booking.yml).
SECRETS="PLATO_API_KEY=plato-api-key:latest,GMAIL_APP_PASSWORD=gmail-app-password:latest"

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
