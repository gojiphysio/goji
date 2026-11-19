#!/usr/bin/env bash
#
# Deploy goji-wa-agent, the WhatsApp assistant's webhook service (Phase 0:
# staging on Meta's test number, then a coexistence test number).
# Run from Cloud Shell or a laptop with gcloud + bq, from the repo root:
#   bash business-intelligence/scripts/wa_agent/deploy.sh
#
# Re-runnable. First run also creates the service account, Firestore database
# + TTL policy, the events table and its grant. Secrets must exist first:
#   anthropic-api-key      Claude API key (Goji workspace)
#   wa-token               WhatsApp access token (Meta system user, or provider key)
#   wa-app-secret          Meta app secret (webhook signature)
#   wa-verify-token        any random string; also typed into Meta's webhook setup
#   wa-agent-admin-token   any random string; for the /admin endpoints
#   gmail-app-password     existing; escalation emails to hello@
#   wa-agent-internal-token  any long random string; shared with goji-booking for
#                          /internal/book and /internal/booking-confirmed
#   printf '%s' '<value>' | gcloud secrets create <name> --data-file=- --project goji-bi
#
# Provider that doesn't forward Meta's signature: create secret
#   wa-webhook-url-token (long random string) and run with USE_URL_TOKEN=1; the
#   provider then posts to <url>/webhook/<token>.
#
# Required env: WA_PHONE_NUMBER_ID. Optional: WA_API_BASE, WA_SEND_PATH,
# WA_AUTH_HEADER, WA_AUTH_PREFIX (provider transport), WA_AGENT_HOURS.
#
# --max-instances=1: the per-chat locks are in-process. --min-instances=1 and
# --no-cpu-throttling: the webhook acks first and works on a background thread,
# which Cloud Run would otherwise starve of CPU (and cold starts cost seconds).

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-wa-agent}"
SA_NAME="wa-agent-sa"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../../.." && pwd)"
: "${WA_PHONE_NUMBER_ID:?set WA_PHONE_NUMBER_ID (Meta app > WhatsApp > API Setup)}"

gcloud config set project "${PROJECT}" >/dev/null

echo "==> 1/6 Knowledge base from the website content"
(cd "${ROOT}/business-intelligence/scripts" && \
  python3 -m wa_agent.kb --site "${ROOT}/marketing/website" --out "${HERE}/_build/kb.json")

echo "==> 2/6 Service account (its own, least privilege: it holds chat transcripts)"
gcloud iam service-accounts describe "${SA}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${SA_NAME}" --display-name="WhatsApp assistant"
for role in roles/datastore.user roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "${PROJECT}" --member="serviceAccount:${SA}" \
    --role="${role}" --condition=None --quiet >/dev/null
done
SECRET_NAMES="anthropic-api-key wa-token wa-app-secret wa-verify-token wa-agent-admin-token gmail-app-password wa-agent-internal-token"
if [[ "${USE_URL_TOKEN:-0}" == "1" ]]; then SECRET_NAMES+=" wa-webhook-url-token"; fi
for s in ${SECRET_NAMES}; do
  gcloud secrets add-iam-policy-binding "${s}" --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
done

echo "==> 3/6 Firestore (chat state) + 30-day TTL on transcripts"
gcloud services enable firestore.googleapis.com --quiet
gcloud firestore databases describe --database="(default)" >/dev/null 2>&1 || \
  gcloud firestore databases create --location="${REGION}" --type=firestore-native --quiet
gcloud firestore fields ttls update expire_at --collection-group=wa_chats \
  --enable-ttl --async --quiet >/dev/null 2>&1 || echo "    (TTL policy already set)"

echo "==> 4/6 Events table + write grant"
bq query --use_legacy_sql=false --quiet \
  < "${ROOT}/business-intelligence/scripts/sql/marts/62_wa_agent_events.sql" >/dev/null
bq add-iam-policy-binding --member="serviceAccount:${SA}" \
  --role=roles/bigquery.dataEditor "${PROJECT}:marts.wa_agent_events" >/dev/null
# Read: returning-patient recognition and "my appointments", by the chat's own
# number only (tools.py). Writes to the calendar go through goji-booking's
# /internal/book (shared token), never to BigQuery or Plato directly.
for t in marts.dim_patient_contact marts.dim_patient stg.appointments; do
  bq add-iam-policy-binding --member="serviceAccount:${SA}" \
    --role=roles/bigquery.dataViewer "${PROJECT}:${t}" >/dev/null
done

echo "==> 5/6 Deploy ${SERVICE}"
ENV_VARS="GCP_PROJECT=${PROJECT},WA_PHONE_NUMBER_ID=${WA_PHONE_NUMBER_ID}"
ENV_VARS+=",WA_AGENT_HOURS=${WA_AGENT_HOURS:-all}"
ENV_VARS+=",WA_AGENT_PATIENT_LOOKUP=1"
# Direct booking writes nothing until this is 0 (goji-booking does a dry run).
ENV_VARS+=",WA_AGENT_BOOKING_DRY_RUN=${WA_AGENT_BOOKING_DRY_RUN:-1}"
if [[ -n "${WA_AGENT_PUBLIC_URL:-}" ]]; then ENV_VARS+=",WA_AGENT_PUBLIC_URL=${WA_AGENT_PUBLIC_URL}"; fi
for v in WA_API_BASE WA_SEND_PATH WA_AUTH_HEADER WA_AUTH_PREFIX; do
  if [[ -n "${!v:-}" ]]; then ENV_VARS+=",${v}=${!v}"; fi
done
SECRETS="ANTHROPIC_API_KEY=anthropic-api-key:latest,WA_TOKEN=wa-token:latest,WA_APP_SECRET=wa-app-secret:latest,WA_VERIFY_TOKEN=wa-verify-token:latest,WA_AGENT_ADMIN_TOKEN=wa-agent-admin-token:latest,GMAIL_APP_PASSWORD=gmail-app-password:latest,WA_AGENT_INTERNAL_TOKEN=wa-agent-internal-token:latest"
if [[ "${USE_URL_TOKEN:-0}" == "1" ]]; then SECRETS+=",WA_WEBHOOK_URL_TOKEN=wa-webhook-url-token:latest"; fi
gcloud run deploy "${SERVICE}" \
  --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --set-env-vars="${ENV_VARS}" \
  --set-secrets="${SECRETS}" \
  --max-instances=1 --min-instances=1 --no-cpu-throttling \
  --allow-unauthenticated \
  --quiet

URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"
echo "==> 6/6 Done"
echo "    Webhook URL for Meta / the provider: ${URL}/webhook"
echo "    Re-run with WA_AGENT_PUBLIC_URL=${URL} so staff emails carry the 👍/👎 links,"
echo "    and set goji-booking's WA_AGENT_URL=${URL} for booking confirmations."
echo "    Subscribe the fields: messages, smb_message_echoes"
