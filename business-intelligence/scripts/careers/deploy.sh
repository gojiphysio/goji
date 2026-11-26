#!/usr/bin/env bash
#
# Deploy goji-careers — the website's job-application backend at
# https://careers-api.gojiphysio.com. Own Cloud Run service (like goji-booking).
#
# Runs as its own service account, careers-sa, which can read only the four
# secrets below: no BigQuery, no Plato, nothing from the patient side. That keeps
# recruitment data apart from patient data (PDPA), and is created on first run.
#
# Secrets (Secret Manager; README.md "One-time setup" says how to make them):
#   careers-google-client-secret   OAuth client secret (Desktop-app client)
#   careers-google-refresh-token   hello@'s refresh token, scope drive.file
#   gmail-app-password             shared with goji-booking (hello@ SMTP)
#   turnstile-secret               shared with goji-booking (Cloudflare Turnstile)
# Plain env (not secret; IDs printed by `python3 -m careers.admin setup`):
#   CAREERS_GOOGLE_CLIENT_ID, CAREERS_DRIVE_ROOT_ID,
#   CAREERS_DRIVE_APPLICATIONS_ID, CAREERS_TRACKER_ID
#   CAREERS_TEST_MODE=1 + CAREERS_TEST_RECIPIENT=<staff inbox> until go-live.
#
# PRIMARY PATH: pushes to `main` touching scripts/careers/** auto-deploy via
# .github/workflows/deploy-careers.yml once the repo variables are set. This
# script is the manual fallback and the first-time standup (it also creates the
# service account and grants). Run from Cloud Shell:
#   CAREERS_GOOGLE_CLIENT_ID=… CAREERS_DRIVE_ROOT_ID=… CAREERS_DRIVE_APPLICATIONS_ID=… \
#   CAREERS_TRACKER_ID=… CAREERS_TEST_MODE=1 CAREERS_TEST_RECIPIENT=… \
#   bash business-intelligence/scripts/careers/deploy.sh
#
# --max-instances=1 keeps the in-process locks authoritative (see Dockerfile).

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-careers}"
DOMAIN="${DOMAIN:-careers-api.gojiphysio.com}"
CORS_ORIGIN="${CORS_ORIGIN:-https://www.gojiphysio.com}"
SA_NAME="careers-sa"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${CAREERS_GOOGLE_CLIENT_ID:?set CAREERS_GOOGLE_CLIENT_ID}"
: "${CAREERS_DRIVE_ROOT_ID:?set CAREERS_DRIVE_ROOT_ID (from careers.admin setup)}"
: "${CAREERS_DRIVE_APPLICATIONS_ID:?set CAREERS_DRIVE_APPLICATIONS_ID}"
: "${CAREERS_TRACKER_ID:?set CAREERS_TRACKER_ID}"
TEST_MODE="${CAREERS_TEST_MODE:-}"
TEST_RECIPIENT="${CAREERS_TEST_RECIPIENT:-}"

gcloud config set project "${PROJECT}" >/dev/null

echo "==> Service account ${SA}"
gcloud iam service-accounts describe "${SA}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="goji-careers runtime (recruitment only)"
for s in careers-google-client-secret careers-google-refresh-token gmail-app-password turnstile-secret; do
  gcloud secrets add-iam-policy-binding "${s}" --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
  echo "    secretAccessor on ${s}"
done

SECRETS="CAREERS_GOOGLE_CLIENT_SECRET=careers-google-client-secret:latest"
SECRETS+=",CAREERS_GOOGLE_REFRESH_TOKEN=careers-google-refresh-token:latest"
SECRETS+=",GMAIL_APP_PASSWORD=gmail-app-password:latest,TURNSTILE_SECRET=turnstile-secret:latest"
# '@'-delimited (gcloud's ^@^ syntax) because CAREERS_EXTRA_ORIGINS holds commas.
ENV="CORS_ORIGIN=${CORS_ORIGIN}@CAREERS_GOOGLE_CLIENT_ID=${CAREERS_GOOGLE_CLIENT_ID}"
ENV+="@CAREERS_DRIVE_ROOT_ID=${CAREERS_DRIVE_ROOT_ID}@CAREERS_DRIVE_APPLICATIONS_ID=${CAREERS_DRIVE_APPLICATIONS_ID}"
ENV+="@CAREERS_TRACKER_ID=${CAREERS_TRACKER_ID}@CAREERS_TEST_MODE=${TEST_MODE}@CAREERS_TEST_RECIPIENT=${TEST_RECIPIENT}"
ENV+="@CAREERS_EXTRA_ORIGINS=${CAREERS_EXTRA_ORIGINS:-}"

echo "==> Deploying ${SERVICE}"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --set-env-vars="^@^${ENV}" \
  --set-secrets="${SECRETS}" \
  --max-instances=1 --min-instances=0 --memory=512Mi --timeout=120 \
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

echo "Done — POST https://${DOMAIN}/api/apply"
