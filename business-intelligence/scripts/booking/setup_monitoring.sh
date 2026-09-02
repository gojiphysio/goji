#!/usr/bin/env bash
#
# Recurring health check for the booking form.
#
# Stands up a Cloud Monitoring uptime check against
#   https://booking.gojiphysio.com/healthcheck/deep
# plus an alert policy that emails when it goes red from more than one probe
# region. Free tier: uptime checks cost nothing at this volume, which keeps this
# on the repo's free/DIY-first rule.
#
# WHY /healthcheck/deep AND NOT /healthcheck:
#   On 2026-09-01 the booking form was down for hours — every availability call
#   502'd — while /healthcheck returned a cheerful 200 the whole time, because
#   it only proves the container is up. /healthcheck/deep actually derives
#   availability from Plato, so it goes red for the thing customers experience.
#
# WHAT TRIPS THE ALERT (the `reason` field in the response body says which):
#   derivation_failed  — Plato threw, or our derivation did. This is the outage
#                        shape: the visitor sees "We couldn't load times just now".
#   no_bookable_dates  — it ran clean but there is nothing bookable in the next
#                        14 days. Almost always a config/roster problem; a
#                        genuinely full fortnight would also trip it, which is
#                        rare enough to be worth knowing about anyway.
#
# Run from Cloud Shell (or any authenticated shell):
#   bash business-intelligence/scripts/booking/setup_monitoring.sh
#   ALERT_EMAIL=someone@gojiphysio.com bash .../setup_monitoring.sh
#
# Re-runnable: reuses an existing channel / uptime check / policy by display
# name instead of creating duplicates.

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
DOMAIN="${DOMAIN:-booking.gojiphysio.com}"
CHECK_PATH="${CHECK_PATH:-/healthcheck/deep}"
# Probe interval in minutes: 1, 5, 10 or 15. 5 matches the deep check's own
# 60s result cache without hammering Plato's 20 req/min budget.
PERIOD_MIN="${PERIOD_MIN:-5}"
ALERT_EMAIL="${ALERT_EMAIL:-hello@gojiphysio.com}"

CHANNEL_NAME="Goji booking alerts (${ALERT_EMAIL})"
UPTIME_NAME="goji-booking readiness"
POLICY_NAME="Booking form down (goji-booking)"

gcloud config set project "${PROJECT}" >/dev/null
gcloud services enable monitoring.googleapis.com --project="${PROJECT}" --quiet

echo "============================================================"
echo " Goji — booking form health check"
echo " Project: ${PROJECT}"
echo " Probe:   https://${DOMAIN}${CHECK_PATH}  every ${PERIOD_MIN} min"
echo " Alerts:  ${ALERT_EMAIL}"
echo "============================================================"

# --- 1. Notification channel -------------------------------------------------
echo
echo "==> Notification channel"
# NB: these Monitoring APIs accept --filter but silently ignore displayName
# ("filter keys were not present in any resource"), so match client-side —
# otherwise every re-run of this script creates another channel/check.
CHANNEL="$(gcloud beta monitoring channels list \
  --project="${PROJECT}" --format="value(name,displayName)" \
  | awk -F'\t' -v n="${CHANNEL_NAME}" '$2 == n {print $1; exit}')"
if [[ -n "${CHANNEL}" ]]; then
  echo "    reusing ${CHANNEL}"
else
  CHANNEL="$(gcloud beta monitoring channels create \
    --project="${PROJECT}" \
    --display-name="${CHANNEL_NAME}" \
    --type=email \
    --channel-labels="email_address=${ALERT_EMAIL}" \
    --format="value(name)")"
  echo "    created ${CHANNEL}"
  echo "    >> Check ${ALERT_EMAIL} and confirm the subscription if Google asks."
fi

# --- 2. Uptime check ---------------------------------------------------------
# Google probes from several regions. A 2xx means the booking form can actually
# produce times; our endpoint returns 503 for both failure reasons above.
echo
echo "==> Uptime check"
CHECK_ID="$(gcloud monitoring uptime list-configs \
  --project="${PROJECT}" --format="value(name,displayName)" \
  | awk -F'\t' -v n="${UPTIME_NAME}" '$2 == n {print $1; exit}' | awk -F/ '{print $NF}')"
if [[ -n "${CHECK_ID}" ]]; then
  echo "    reusing ${CHECK_ID}"
else
  gcloud monitoring uptime create "${UPTIME_NAME}" \
    --project="${PROJECT}" \
    --resource-type=uptime-url \
    --resource-labels="host=${DOMAIN},project_id=${PROJECT}" \
    --protocol=https \
    --path="${CHECK_PATH}" \
    --port=443 \
    --period="${PERIOD_MIN}" \
    --timeout=30 \
    --status-classes=2xx \
    --quiet
  CHECK_ID="$(gcloud monitoring uptime list-configs \
    --project="${PROJECT}" --format="value(name,displayName)" \
    | awk -F'\t' -v n="${UPTIME_NAME}" '$2 == n {print $1; exit}' | awk -F/ '{print $NF}')"
  echo "    created ${CHECK_ID}"
fi
[[ -n "${CHECK_ID}" ]] || { echo "!! could not resolve the uptime check id"; exit 1; }

# --- 3. Alert policy ---------------------------------------------------------
# Fires when >1 probe region has been failing for 5 minutes. Requiring two
# regions filters the single-region blips that would otherwise page the clinic
# for a network hiccup rather than a real outage.
echo
echo "==> Alert policy"
# Alert policies live in the alpha surface; install it the same way deploy.sh
# installs beta, or this step dies on a non-interactive "do you want to
# continue?" prompt.
gcloud components install alpha --quiet >/dev/null 2>&1 || true
EXISTING_POLICY="$(gcloud alpha monitoring policies list \
  --project="${PROJECT}" --format="value(name,displayName)" \
  | awk -F'\t' -v n="${POLICY_NAME}" '$2 == n {print $1; exit}')"

POLICY_FILE="$(mktemp)"
trap 'rm -f "${POLICY_FILE}"' EXIT
cat > "${POLICY_FILE}" <<EOF
displayName: "${POLICY_NAME}"
documentation:
  mimeType: text/markdown
  content: |
    **https://${DOMAIN}${CHECK_PATH} is failing** — the /book form on the website
    most likely cannot load appointment times.

    Open the endpoint and read \`reason\`:

        curl -s https://${DOMAIN}${CHECK_PATH} | jq

    * \`derivation_failed\` — Plato threw or rate-limited us. Check the logs:
      \`gcloud logging read 'resource.labels.service_name=goji-booking AND severity>=WARNING' --project=${PROJECT} --limit=20 --freshness=1h\`
    * \`no_bookable_dates\` — the derivation ran but the calendar is empty.
      Suspect clinician rules/roster in Plato, not the service.

    Runbook: \`business-intelligence/scripts/booking/DIAGNOSIS.md\`
combiner: OR
conditions:
  - displayName: "${DOMAIN}${CHECK_PATH} failing in more than one region"
    conditionThreshold:
      filter: >-
        metric.type="monitoring.googleapis.com/uptime_check/check_passed"
        AND resource.type="uptime_url"
        AND metric.label.check_id="${CHECK_ID}"
      aggregations:
        - alignmentPeriod: 300s
          perSeriesAligner: ALIGN_NEXT_OLDER
          crossSeriesReducer: REDUCE_COUNT_FALSE
          groupByFields:
            - resource.label.host
      comparison: COMPARISON_GT
      thresholdValue: 1
      duration: 300s
      trigger:
        count: 1
notificationChannels:
  - ${CHANNEL}
alertStrategy:
  autoClose: 604800s
EOF

if [[ -n "${EXISTING_POLICY}" ]]; then
  gcloud alpha monitoring policies update "${EXISTING_POLICY}" \
    --project="${PROJECT}" --policy-from-file="${POLICY_FILE}" --quiet
  echo "    updated ${EXISTING_POLICY}"
else
  gcloud alpha monitoring policies create \
    --project="${PROJECT}" --policy-from-file="${POLICY_FILE}" --quiet
  echo "    created"
fi

echo
echo "============================================================"
echo " Done. Verify the probe right now:"
echo "   curl -s https://${DOMAIN}${CHECK_PATH} | jq"
echo " Uptime dashboard:"
echo "   https://console.cloud.google.com/monitoring/uptime?project=${PROJECT}"
echo "============================================================"
