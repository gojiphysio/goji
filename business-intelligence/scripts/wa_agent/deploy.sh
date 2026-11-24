#!/usr/bin/env bash
#
# Deploy goji-wa-agent, the WhatsApp assistant's webhook service, plus its
# 07:30 morning-summary schedule.
# Run from Cloud Shell or a laptop with gcloud + bq, from the repo root:
#   bash business-intelligence/scripts/wa_agent/deploy.sh
#
# Re-runnable. First run also creates the service account, Firestore database
# + TTL policy, the events table and its grant. Secrets must exist first: run
#   bash business-intelligence/scripts/wa_agent/setup_secrets.sh
# once (it creates every secret below and says which values go where).
#   anthropic-api-key         Claude API key (Goji workspace)
#   wa-token                  WhatsApp access token (Meta system user, or provider key)
#   wa-app-secret             Meta app secret (webhook signature)
#   wa-verify-token           random; also typed into Meta's webhook setup
#   wa-agent-admin-token      random; X-Admin-Token for /admin and /internal/morning-summary
#   gmail-app-password        existing; escalation emails to hello@
#   wa-agent-internal-token   random; shared with goji-booking for /internal/book
#                             and /internal/booking-confirmed
#   wa-agent-hash-salt        random; keys chat_key in marts.wa_agent_events. NEVER rotate
#   wa-agent-feedback-secret  random; signs the one-tap feedback links in staff emails
#
# Provider that doesn't forward Meta's signature: create secret
#   wa-webhook-url-token (setup_secrets.sh does, with USE_URL_TOKEN=1) and run
#   with USE_URL_TOKEN=1; the provider then posts to <url>/webhook/<token>.
#
# ENVIRONMENT VARIABLES: set in the shell = applied; unset = the live value is
# kept. This script never resets a value you didn't pass. Personal numbers
# (WA_AGENT_STAFF, WA_AGENT_TESTERS) live in a private env file on the
# operator's machine, never in the repo; source it first:
#   set -a; . ~/.config/goji-wa-agent/prod.env; set +a
#   First deploy only: WA_PHONE_NUMBER_ID is required (unless WA_SEND_PATH has
#   no {phone_number_id}, as with 360dialog).
#   Passed through when set (an empty value counts as set, e.g. WA_AUTH_PREFIX=
#   for a provider's raw key, or WA_AGENT_TESTERS= to clear the list):
#     WA_PHONE_NUMBER_ID WA_API_BASE WA_SEND_PATH WA_AUTH_HEADER WA_AUTH_PREFIX
#     WA_AGENT_STAFF WA_AGENT_TESTERS WA_AGENT_ALWAYS_HUMAN WA_AGENT_GOLIVE_LOOKBACK_DAYS
#     WA_AGENT_STAGE WA_AGENT_CONTACT_SCOPE WA_AGENT_GO_LIVE
#     WA_AGENT_STAFF_TEMPLATE WA_AGENT_CONFIRMATIONS WA_AGENT_PUBLIC_URL
#     WA_AGENT_BOOKING_DRY_RUN WA_AGENT_HOURS WA_AGENT_PATIENT_LOOKUP
#   Defaults, used only when neither the shell nor the live service has a value:
#     WA_AGENT_HOURS=all  WA_AGENT_PATIENT_LOOKUP=1  WA_AGENT_BOOKING_DRY_RUN=0
#     (direct booking is on from day one: owner's decision, 19 Nov 2026)
#     WA_AGENT_PUBLIC_URL=<the service URL> (set right after the first deploy)
#   Stage, contact scope and hours also live in Firestore flags (GET/POST
#   /admin/rollout); the env value is only the default the flags fall back to.
#   To delete a variable outright:
#     gcloud run services update goji-wa-agent --region asia-southeast1 --remove-env-vars=NAME
#
# Other knobs: USE_URL_TOKEN=1 (above), MORNING_SUMMARY=0 (skip the scheduler
# step), MORNING_IMAGE (image for the summary job, any image with sh + curl).
#
# --max-instances=1: the per-chat locks are in-process. CPU only during
# requests (Charles 19 Nov 2026: no always-on CPU): the webhook queues each
# event on Cloud Tasks (queue below) and acks; the queue calls /tasks/run and
# the turn runs inside that request, so CPU is billed only while working.
# --min-instances=1 keeps one idle instance (cheap with CPU throttled): a cold
# start measured 19s (23 Nov 2026), and Meta / Dualhook give up on a webhook
# after ~5s. --cpu-boost speeds up the restarts that still happen.
# --timeout=300: a turn is ~40s; room for a slow model call.
# CI (.github/workflows/deploy-wa-agent.yml) rolls code with the same flags once
# this script has created the service.

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-wa-agent}"
SA_NAME="wa-agent-sa"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
SCHEDULER_SA="scheduler-sa@${PROJECT}.iam.gserviceaccount.com"
SUMMARY_JOB="wa-agent-morning-summary"
QUEUE="${QUEUE:-wa-agent}"
SUMMARY_SCHEDULE="wa-agent-morning-summary-daily"
MORNING_IMAGE="${MORNING_IMAGE:-gcr.io/google.com/cloudsdktool/google-cloud-cli:slim}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../../.." && pwd)"

gcloud config set project "${PROJECT}" >/dev/null

echo "==> 1/7 Knowledge base from the website content"
(cd "${ROOT}/business-intelligence/scripts" && \
  python3 -m wa_agent.kb --site "${ROOT}/marketing/website" --out "${HERE}/_build/kb.json")

echo "==> 2/7 Service account (its own, least privilege: it holds chat transcripts)"
gcloud iam service-accounts describe "${SA}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${SA_NAME}" --display-name="WhatsApp assistant"
for role in roles/datastore.user roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "${PROJECT}" --member="serviceAccount:${SA}" \
    --role="${role}" --condition=None --quiet >/dev/null
done
# Every secret the service mounts. Keep in step with SECRETS below and with
# deploy-wa-agent.yml.
SECRET_NAMES="anthropic-api-key wa-token wa-app-secret wa-verify-token wa-agent-admin-token gmail-app-password wa-agent-internal-token wa-agent-hash-salt wa-agent-feedback-secret"
if [[ "${USE_URL_TOKEN:-0}" == "1" ]]; then SECRET_NAMES+=" wa-webhook-url-token"; fi
for s in ${SECRET_NAMES}; do
  gcloud secrets add-iam-policy-binding "${s}" --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
done

echo "==> 3/7 Firestore (chat state) + 30-day TTL on transcripts"
gcloud services enable firestore.googleapis.com --quiet
gcloud firestore databases describe --database="(default)" >/dev/null 2>&1 || \
  gcloud firestore databases create --location="${REGION}" --type=firestore-native --quiet
gcloud firestore fields ttls update expire_at --collection-group=wa_chats \
  --enable-ttl --async --quiet >/dev/null 2>&1 || echo "    (TTL policy already set)"
# Pause records for paused chats (no text), kept a year (state.HOLD_DAYS).
gcloud firestore fields ttls update expire_at --collection-group=wa_chats_holds \
  --enable-ttl --async --quiet >/dev/null 2>&1 || echo "    (holds TTL policy already set)"

echo "==> 4/7 Events table + write grant"
bq query --use_legacy_sql=false --quiet \
  < "${ROOT}/business-intelligence/scripts/sql/marts/62_wa_agent_events.sql" >/dev/null
bq add-iam-policy-binding --member="serviceAccount:${SA}" \
  --role=roles/bigquery.dataEditor "${PROJECT}:marts.wa_agent_events" >/dev/null
# Read: returning-patient recognition and "my appointments", by the chat's own
# number only (tools.py). Writes to the calendar go through goji-booking's
# /internal/book (shared token), never to BigQuery or Plato directly.
for t in marts.dim_patient_contact marts.patient_contact_live marts.dim_patient stg.appointments; do
  bq add-iam-policy-binding --member="serviceAccount:${SA}" \
    --role=roles/bigquery.dataViewer "${PROJECT}:${t}" >/dev/null
done

echo "==> 5/7 Cloud Tasks queue ${QUEUE} + deploy ${SERVICE}"
gcloud services enable cloudtasks.googleapis.com --quiet
# Retries are harmless (webhook de-dupe by message id) and help across a cold
# start; /tasks/run answers 200 for anything it accepted.
QUEUE_FLAGS=(--location="${REGION}" --max-attempts=3 --min-backoff=5s
             --max-concurrent-dispatches=10)
if gcloud tasks queues describe "${QUEUE}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud tasks queues update "${QUEUE}" "${QUEUE_FLAGS[@]}" --quiet >/dev/null
else
  gcloud tasks queues create "${QUEUE}" "${QUEUE_FLAGS[@]}" --quiet >/dev/null
fi
# Plain HTTP tasks signed in the body (tasks.py), so enqueuer is the only grant:
# no OIDC token, so no actAs on any service account.
gcloud tasks queues add-iam-policy-binding "${QUEUE}" --location="${REGION}" \
  --member="serviceAccount:${SA}" --role=roles/cloudtasks.enqueuer --quiet >/dev/null
export WA_AGENT_TASKS_QUEUE="projects/${PROJECT}/locations/${REGION}/queues/${QUEUE}"
# Why --update-env-vars and not --set-env-vars: --set-env-vars replaces the
# service's whole env block, so every deploy had to repeat every value, and
# anything set by hand since (a tester added, the stage moved on) was silently
# reset to whatever this script's caller remembered to pass. That is the trap
# deploy-dashboard.yml documents for the reminders job.
# Instead: read the live env back, send only (a) what the caller set in the
# shell and (b) a default for a variable the service doesn't have yet. gcloud
# merges that into the live block and leaves everything else alone. The same
# rule works for the first deploy (no live env: defaults fill in) and every
# one after. Pairs are joined with '@@' (gcloud's ^DELIM^ syntax) because the
# contact lists are comma-separated and staff entries may contain '@'.
LIVE_JSON="$(gcloud run services describe "${SERVICE}" --region="${REGION}" \
  --format=json 2>/dev/null || true)"
if [[ -n "${LIVE_JSON}" ]]; then FIRST_DEPLOY=0; else FIRST_DEPLOY=1; fi
MERGE_PY="$(mktemp)"
trap 'rm -f "${MERGE_PY}"' EXIT
cat > "${MERGE_PY}" <<'PY'
import json, os, sys

PASSTHROUGH = [
    "WA_PHONE_NUMBER_ID", "WA_API_BASE", "WA_SEND_PATH", "WA_AUTH_HEADER", "WA_AUTH_PREFIX",
    "WA_AGENT_STAFF", "WA_AGENT_TESTERS", "WA_AGENT_ALWAYS_HUMAN", "WA_AGENT_GOLIVE_LOOKBACK_DAYS",
    "WA_AGENT_STAGE", "WA_AGENT_CONTACT_SCOPE", "WA_AGENT_GO_LIVE",
    "WA_AGENT_STAFF_TEMPLATE", "WA_AGENT_CONFIRMATIONS", "WA_AGENT_PUBLIC_URL",
    "WA_AGENT_BOOKING_DRY_RUN", "WA_AGENT_HOURS", "WA_AGENT_PATIENT_LOOKUP",
    "WA_AGENT_TASKS_QUEUE",
]
DEFAULTS = {"WA_AGENT_HOURS": "all", "WA_AGENT_PATIENT_LOOKUP": "1",
            "WA_AGENT_BOOKING_DRY_RUN": "0"}
# Phone-number lists: report a count, not the numbers.
LISTS = {"WA_AGENT_STAFF", "WA_AGENT_TESTERS", "WA_AGENT_ALWAYS_HUMAN"}

live = {}
raw = os.environ.get("LIVE_JSON", "").strip()
if raw:
    spec = json.loads(raw).get("spec", {}).get("template", {}).get("spec", {})
    for c in (spec.get("containers") or [])[:1]:
        for e in c.get("env") or []:
            if "valueFrom" not in e:          # secret refs belong to --update-secrets
                live[e["name"]] = e.get("value", "")

update = {"GCP_PROJECT": os.environ["PROJECT"]}
effective = dict(live)
for name in PASSTHROUGH:
    if name in os.environ:
        update[name] = effective[name] = os.environ[name]
        src = "set now"
    elif name in live:
        src = "kept (live)"
    elif name in DEFAULTS:
        update[name] = effective[name] = DEFAULTS[name]
        src = "default"
    else:
        continue
    v = effective[name]
    shown = f"{len([p for p in v.split(',') if p.strip()])} entries" if name in LISTS else repr(v)
    print(f"    {name:<26} {shown:<34} {src}", file=sys.stderr)

send_path = effective.get("WA_SEND_PATH", "/{phone_number_id}/messages")
if "{phone_number_id}" in send_path and not effective.get("WA_PHONE_NUMBER_ID"):
    sys.exit("!! set WA_PHONE_NUMBER_ID (Meta app > WhatsApp > API Setup) for the first deploy")
if effective.get("WA_AGENT_BOOKING_DRY_RUN", "0").strip().lower() in ("1", "true", "yes", "on"):
    print("    !! WA_AGENT_BOOKING_DRY_RUN is on: direct booking writes nothing to Plato.\n"
          "       Re-run with WA_AGENT_BOOKING_DRY_RUN=0 to turn it on.", file=sys.stderr)
for k, v in update.items():
    if "@@" in v:
        sys.exit(f"!! {k} contains '@@', which this script uses as the pair delimiter")
print("^@@^" + "@@".join(f"{k}={v}" for k, v in update.items()))
PY
ENV_UPDATE="$(LIVE_JSON="${LIVE_JSON}" PROJECT="${PROJECT}" python3 "${MERGE_PY}")"
SECRETS="ANTHROPIC_API_KEY=anthropic-api-key:latest,WA_TOKEN=wa-token:latest,WA_APP_SECRET=wa-app-secret:latest,WA_VERIFY_TOKEN=wa-verify-token:latest,WA_AGENT_ADMIN_TOKEN=wa-agent-admin-token:latest,GMAIL_APP_PASSWORD=gmail-app-password:latest,WA_AGENT_INTERNAL_TOKEN=wa-agent-internal-token:latest,WA_AGENT_HASH_SALT=wa-agent-hash-salt:latest,WA_AGENT_FEEDBACK_SECRET=wa-agent-feedback-secret:latest"
if [[ "${USE_URL_TOKEN:-0}" == "1" ]]; then SECRETS+=",WA_WEBHOOK_URL_TOKEN=wa-webhook-url-token:latest"; fi
# --update-secrets for the same reason: it adds/refreshes these mounts and
# keeps any other (e.g. WA_WEBHOOK_URL_TOKEN from an earlier USE_URL_TOKEN=1 run).
gcloud run deploy "${SERVICE}" \
  --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --update-env-vars="${ENV_UPDATE}" \
  --update-secrets="${SECRETS}" \
  --max-instances=1 --min-instances=1 --cpu-throttling --cpu-boost --timeout=300 \
  --allow-unauthenticated \
  --quiet

URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"
# Staff emails carry one-tap feedback links built from WA_AGENT_PUBLIC_URL. The
# URL only exists after the first deploy, so fill it in then (one more revision,
# first deploy only). An explicit WA_AGENT_PUBLIC_URL (a custom domain) wins.
LIVE_PUBLIC_URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" \
  --format='value(spec.template.spec.containers[0].env.filter("name:WA_AGENT_PUBLIC_URL").extract(value))' \
  2>/dev/null || true)"
if [[ -z "${LIVE_PUBLIC_URL}" && -z "${WA_AGENT_PUBLIC_URL+x}" ]]; then
  echo "    setting WA_AGENT_PUBLIC_URL=${URL}"
  gcloud run services update "${SERVICE}" --region="${REGION}" \
    --update-env-vars="WA_AGENT_PUBLIC_URL=${URL}" --quiet >/dev/null
fi

echo "==> 6/7 Morning summary: ${SUMMARY_JOB} job, run daily 07:30 Asia/Singapore"
# Why a Cloud Run job and not a Scheduler HTTP target with the header:
# Scheduler would store X-Admin-Token in the scheduler job's own config, where
# anyone with project Viewer reads it (`gcloud scheduler jobs describe`), and
# the create/update calls carry it into audit logs. Here the token never leaves
# Secret Manager: Scheduler only calls the Cloud Run Admin API (OAuth as
# scheduler-sa, the pattern the reminders job uses), and the job reads the token
# from its secret mount at run time. curl prints neither the header nor the
# response body (which may summarise chats); -f turns a non-2xx into a failed
# execution, which the error alert in setup_monitoring.sh does not cover, so
# check Cloud Run > Jobs if summaries stop arriving.
if [[ "${MORNING_SUMMARY:-1}" == "1" ]]; then
  gcloud services enable cloudscheduler.googleapis.com --quiet
  CURL_CMD='curl -fsS -o /dev/null --max-time 240 -X POST -H "X-Admin-Token: ${WA_AGENT_ADMIN_TOKEN}" "${WA_AGENT_URL}/internal/morning-summary" && echo "morning summary requested"'
  gcloud run jobs deploy "${SUMMARY_JOB}" \
    --region="${REGION}" --image="${MORNING_IMAGE}" \
    --service-account="${SA}" \
    --set-env-vars="WA_AGENT_URL=${URL}" \
    --set-secrets="WA_AGENT_ADMIN_TOKEN=wa-agent-admin-token:latest" \
    --command=/bin/sh --args="^@@^-c@@${CURL_CMD}" \
    --max-retries=1 --task-timeout=300s \
    --quiet
  gcloud iam service-accounts describe "${SCHEDULER_SA}" >/dev/null 2>&1 || \
    gcloud iam service-accounts create scheduler-sa --display-name="Cloud Scheduler invoker"
  gcloud run jobs add-iam-policy-binding "${SUMMARY_JOB}" --region="${REGION}" \
    --member="serviceAccount:${SCHEDULER_SA}" --role=roles/run.invoker --quiet >/dev/null
  RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/${SUMMARY_JOB}:run"
  SCHED_FLAGS=(--location="${REGION}" --schedule="30 7 * * *" --time-zone="Asia/Singapore"
               --uri="${RUN_URI}" --http-method=POST
               --oauth-service-account-email="${SCHEDULER_SA}")
  if gcloud scheduler jobs describe "${SUMMARY_SCHEDULE}" --location="${REGION}" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "${SUMMARY_SCHEDULE}" "${SCHED_FLAGS[@]}" --quiet >/dev/null
    echo "    schedule ${SUMMARY_SCHEDULE} updated"
  else
    gcloud scheduler jobs create http "${SUMMARY_SCHEDULE}" "${SCHED_FLAGS[@]}" --quiet >/dev/null
    echo "    schedule ${SUMMARY_SCHEDULE} created"
  fi
  echo "    Try it now: gcloud run jobs execute ${SUMMARY_JOB} --region ${REGION} --wait"
else
  echo "    skipped (MORNING_SUMMARY=0)"
fi

echo "==> 7/7 Done"
echo "    Webhook URL for Meta / the provider: ${URL}/webhook"
if [[ "${FIRST_DEPLOY}" == "1" ]]; then
  echo "    First deploy. Next:"
  echo "      - GitHub repo variable WA_AGENT_URL=${URL} (goji-booking then mounts the"
  echo "        internal token and sends booking confirmations here)"
  echo "      - bash business-intelligence/scripts/wa_agent/setup_monitoring.sh"
  echo "      - from now on, merges to main redeploy via deploy-wa-agent.yml"
fi
echo "    Subscribe the fields: messages, smb_message_echoes, history (the go-live cut-off reads it)"
echo "    The assistant answers nobody until go-live is set:"
echo "      curl -X POST -H \"X-Admin-Token: \$TOKEN\" ${URL}/admin/go-live"
