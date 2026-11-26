#!/usr/bin/env bash
#
# Deploy goji-careers: the website's job-application backend at
# https://careers-api.gojiphysio.com (POST /api/applications). It stores CVs in
# the recruitment Shared Drive, appends a row to the applicant tracker sheet,
# and sends the internal + acknowledgement emails. Nothing else.
#
# MANUAL deploy only (no CI deploy yet): the integration must be tested end to
# end in test mode first (README.md "Go-live checklist"). Run from Cloud Shell:
#
#   RECRUITMENT_APPLICATIONS_FOLDER_ID=... RECRUITMENT_TRACKER_SHEET_ID=... \
#   CAREERS_TEST_MODE=1 CAREERS_TEST_EMAIL=you@gojiphysio.com \
#     bash business-intelligence/scripts/careers/deploy.sh
#
# Runs as its OWN service account, careers-sa, which has no BigQuery access and
# reaches only the recruitment Shared Drive (added there as a Content manager).
# Secrets (Secret Manager; careers-sa needs secretAccessor on each):
#   gmail-app-password   (required)  hello@ app password, internal + ack emails
#   turnstile-secret     (required)  Cloudflare Turnstile secret (bot check)
#   google-oauth-client  (only with GOOGLE_AUTH_MODE=oauth) JSON with
#                        client_id, client_secret, refresh_token for hello@
#
# --max-instances=1 keeps the reference-number lock and the in-memory rate
# limits authoritative. Do NOT raise it without moving both to a shared store.

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-careers}"
DOMAIN="${DOMAIN:-careers-api.gojiphysio.com}"
CORS_ORIGIN="${CORS_ORIGIN:-https://www.gojiphysio.com}"
GOOGLE_AUTH_MODE="${GOOGLE_AUTH_MODE:-service_account}"
CAREERS_TEST_MODE="${CAREERS_TEST_MODE:-1}"     # default ON: flip only at go-live
CAREERS_TEST_EMAIL="${CAREERS_TEST_EMAIL:-}"
CAREERS_ADMIN_EMAIL="${CAREERS_ADMIN_EMAIL:-hello@gojiphysio.com}"
: "${RECRUITMENT_APPLICATIONS_FOLDER_ID:?set it (printed by careers.setup_workspace)}"
: "${RECRUITMENT_TRACKER_SHEET_ID:?set it (printed by careers.setup_workspace)}"
SA_NAME="careers-sa"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

gcloud config set project "${PROJECT}" >/dev/null

if ! gcloud iam service-accounts describe "${SA}" >/dev/null 2>&1; then
  echo "==> Creating ${SA}"
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Goji careers form (Drive + Sheets only)"
  echo "    >> Add ${SA} to the recruitment Shared Drive as Content manager."
fi
for s in gmail-app-password turnstile-secret; do
  gcloud secrets add-iam-policy-binding "${s}" --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
done

SECRETS="GMAIL_APP_PASSWORD=gmail-app-password:latest,TURNSTILE_SECRET=turnstile-secret:latest"
if [[ "${GOOGLE_AUTH_MODE}" == "oauth" ]]; then
  gcloud secrets add-iam-policy-binding google-oauth-client --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
  SECRETS+=",GOOGLE_OAUTH_CLIENT_JSON=google-oauth-client:latest"
fi

# '^@^' makes '@' the list delimiter, so the comma-separated CORS_ORIGIN survives.
ENV="^@^CORS_ORIGIN=${CORS_ORIGIN}@GOOGLE_AUTH_MODE=${GOOGLE_AUTH_MODE}"
ENV+="@RECRUITMENT_APPLICATIONS_FOLDER_ID=${RECRUITMENT_APPLICATIONS_FOLDER_ID}"
ENV+="@RECRUITMENT_TRACKER_SHEET_ID=${RECRUITMENT_TRACKER_SHEET_ID}"
ENV+="@CAREERS_TEST_MODE=${CAREERS_TEST_MODE}@CAREERS_TEST_EMAIL=${CAREERS_TEST_EMAIL}"
ENV+="@CAREERS_ADMIN_EMAIL=${CAREERS_ADMIN_EMAIL}"

echo "==> Deploying ${SERVICE} (test mode: ${CAREERS_TEST_MODE})"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --set-env-vars="${ENV}" \
  --set-secrets="${SECRETS}" \
  --max-instances=1 --min-instances=0 \
  --memory=512Mi --timeout=120 \
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
  echo "    >> Add DNS on gojiphysio.com:  careers-api  CNAME  ghs.googlehosted.com."
fi

echo "Done. Health: https://${DOMAIN}/healthcheck"
echo "The site form stays on the email fallback until Cloudflare Pages has"
echo "PUBLIC_CAREERS_API=https://${DOMAIN} and the site is rebuilt."
