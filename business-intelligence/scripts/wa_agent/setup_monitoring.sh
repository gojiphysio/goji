#!/usr/bin/env bash
#
# Monitoring for goji-wa-agent, the WhatsApp assistant. Mirrors
# booking/setup_monitoring.sh. Creates, all emailing ALERT_EMAIL:
#   1. an uptime check on <service url>/healthcheck + an alert when it fails
#      from more than one region (the container is down or not serving)
#   2. a log alert on errors from the service: Cloud Run's own ERROR entries
#      (5xx requests, crashes) and the app's ERROR lines / tracebacks
#   3. a log alert on the `send_failed` event (a reply or template didn't go
#      out; the customer got a holding reply at best)
#   4. "no inbound message for 6 daytime hours": a log-based counter of
#      `inbound` events and a PromQL alert that only evaluates while the
#      trailing 6 hours sit inside 08:00-21:00 SGT, Monday to Saturday. A quiet
#      night or Sunday never pages anyone; a dead webhook in clinic hours does.
#
# Why text filters: the app logs plain text (logging.basicConfig in app.py), so
# Cloud Run records its lines with severity DEFAULT, never ERROR. Matching
# severity>=ERROR alone would only see request 5xx and platform errors.
# events.record() logs every event as `event {"event_id": ..., "event": "<name>", ...}`
# (json.dumps, default separators), which is what filters 3 and 4 match.
#
# Run from Cloud Shell after the first deploy (it needs the service URL):
#   bash business-intelligence/scripts/wa_agent/setup_monitoring.sh
#   ALERT_EMAIL=someone@gojiphysio.com bash .../setup_monitoring.sh
#   SILENCE_ALERT=0 bash ...   # skip alert 4 (e.g. before real customer traffic)
#
# Re-runnable: reuses an existing channel / uptime check / metric / policy by
# name instead of creating duplicates, and updates policies in place.

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-wa-agent}"
ALERT_EMAIL="${ALERT_EMAIL:-hello@gojiphysio.com}"
PERIOD_MIN="${PERIOD_MIN:-5}"          # uptime probe interval: 1, 5, 10 or 15
SILENCE_ALERT="${SILENCE_ALERT:-1}"

UPTIME_NAME="goji-wa-agent healthcheck"
POLICY_UPTIME="WhatsApp assistant down (goji-wa-agent)"
POLICY_ERRORS="WhatsApp assistant errors (goji-wa-agent)"
POLICY_SEND="WhatsApp send failed (goji-wa-agent)"
POLICY_SILENCE="WhatsApp assistant: no inbound messages for 6 daytime hours"
INBOUND_METRIC="wa_agent_inbound"

gcloud config set project "${PROJECT}" >/dev/null
gcloud services enable monitoring.googleapis.com logging.googleapis.com \
  --project="${PROJECT}" --quiet
# Alert policies live in the alpha surface; install it non-interactively.
gcloud components install alpha --quiet >/dev/null 2>&1 || true

URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" \
  --format='value(status.url)' 2>/dev/null || true)"
[[ -n "${URL}" ]] || { echo "!! ${SERVICE} not found in ${REGION}: run deploy.sh first"; exit 1; }
HOST="${URL#https://}"
SVC_FILTER="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${SERVICE}\""

echo "============================================================"
echo " Goji — WhatsApp assistant monitoring"
echo " Project: ${PROJECT}"
echo " Probe:   ${URL}/healthcheck  every ${PERIOD_MIN} min"
echo " Alerts:  ${ALERT_EMAIL}"
echo "============================================================"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

# create-or-update an alert policy from a YAML file, matched by display name.
apply_policy() {  # display name, file
  local existing
  existing="$(gcloud alpha monitoring policies list --project="${PROJECT}" \
    --format="value(name,displayName)" | awk -F'\t' -v n="$1" '$2 == n {print $1; exit}')"
  if [[ -n "${existing}" ]]; then
    gcloud alpha monitoring policies update "${existing}" \
      --project="${PROJECT}" --policy-from-file="$2" --quiet >/dev/null
    echo "    updated: $1"
  else
    gcloud alpha monitoring policies create \
      --project="${PROJECT}" --policy-from-file="$2" --quiet >/dev/null
    echo "    created: $1"
  fi
}

# --- 1. Notification channel -------------------------------------------------
# Reuse ANY email channel already pointed at ALERT_EMAIL (booking's monitoring
# made one for hello@), so the inbox isn't asked to confirm a second one. Match
# client-side: these APIs ignore --filter on displayName/labels.
echo
echo "==> Notification channel"
CHANNEL="$(gcloud beta monitoring channels list --project="${PROJECT}" \
  --format="value(name,type,labels.email_address)" \
  | awk -F'\t' -v e="${ALERT_EMAIL}" '$2 == "email" && $3 == e {print $1; exit}')"
if [[ -n "${CHANNEL}" ]]; then
  echo "    reusing ${CHANNEL}"
else
  CHANNEL="$(gcloud beta monitoring channels create --project="${PROJECT}" \
    --display-name="Goji alerts (${ALERT_EMAIL})" --type=email \
    --channel-labels="email_address=${ALERT_EMAIL}" --format="value(name)")"
  echo "    created ${CHANNEL}"
  echo "    >> Check ${ALERT_EMAIL} and confirm the subscription if Google asks."
fi

# --- 2. Uptime check + alert -------------------------------------------------
echo
echo "==> Uptime check"
find_check() {
  gcloud monitoring uptime list-configs --project="${PROJECT}" \
    --format="value(name,displayName)" \
    | awk -F'\t' -v n="${UPTIME_NAME}" '$2 == n {print $1; exit}' | awk -F/ '{print $NF}'
}
CHECK_ID="$(find_check)"
if [[ -n "${CHECK_ID}" ]]; then
  echo "    reusing ${CHECK_ID}"
else
  gcloud monitoring uptime create "${UPTIME_NAME}" --project="${PROJECT}" \
    --resource-type=uptime-url --resource-labels="host=${HOST},project_id=${PROJECT}" \
    --protocol=https --path=/healthcheck --port=443 \
    --period="${PERIOD_MIN}" --timeout=10 --status-classes=2xx --quiet
  CHECK_ID="$(find_check)"
  echo "    created ${CHECK_ID}"
fi
[[ -n "${CHECK_ID}" ]] || { echo "!! could not resolve the uptime check id"; exit 1; }

cat > "${TMP}/uptime.yaml" <<EOF
displayName: "${POLICY_UPTIME}"
documentation:
  mimeType: text/markdown
  content: |
    **${URL}/healthcheck is failing from more than one region.** WhatsApp
    messages to the clinic are not being answered by the assistant (Meta keeps
    retrying the webhook for a while; Chris still sees every message in the
    WhatsApp Business app).

    * Service status and recent revisions:
      \`gcloud run services describe ${SERVICE} --region ${REGION}\`
    * Logs: \`gcloud run services logs read ${SERVICE} --region ${REGION} --limit 50\`
    * Roll back: Cloud Run > ${SERVICE} > Revisions > route 100% to the last good one.
combiner: OR
conditions:
  - displayName: "${HOST}/healthcheck failing in more than one region"
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
apply_policy "${POLICY_UPTIME}" "${TMP}/uptime.yaml"

# --- 3. Errors (log-based alert) ---------------------------------------------
# At most one email per 30 minutes per policy (notificationRateLimit), so a
# crash loop is one message, not hundreds.
echo
echo "==> Error log alert"
cat > "${TMP}/errors.yaml" <<EOF
displayName: "${POLICY_ERRORS}"
documentation:
  mimeType: text/markdown
  content: |
    **goji-wa-agent logged an error.** Customers should have had a holding reply
    and Chris an escalation email (every failure becomes an escalation), but
    look at what broke:

        gcloud logging read '${SVC_FILTER} AND (severity>=ERROR OR textPayload:" ERROR ")' --project=${PROJECT} --limit=20 --freshness=1h

    Kill switch if replies are going wrong: \`POST /admin/kill {"on": true}\`
    (wa_agent/README.md, Runbook).
combiner: OR
conditions:
  - displayName: "ERROR from ${SERVICE}"
    conditionMatchedLog:
      filter: >-
        ${SVC_FILTER}
        AND (severity>=ERROR OR textPayload:" ERROR " OR textPayload:"Traceback (most recent call last)")
notificationChannels:
  - ${CHANNEL}
alertStrategy:
  notificationRateLimit:
    period: 1800s
  autoClose: 1800s
EOF
apply_policy "${POLICY_ERRORS}" "${TMP}/errors.yaml"

# --- 4. send_failed (log-based alert) ----------------------------------------
echo
echo "==> send_failed alert"
cat > "${TMP}/send.yaml" <<EOF
displayName: "${POLICY_SEND}"
documentation:
  mimeType: text/markdown
  content: |
    **A WhatsApp send failed** (event \`send_failed\`; \`reason\` is the exception
    class). Usual causes: the token expired or was revoked (401), the customer's
    24-hour window closed, or the provider is down.

        gcloud logging read '${SVC_FILTER} AND textPayload:"\\"event\\": \\"send_failed\\""' --project=${PROJECT} --limit=20 --freshness=6h

    Replace the token: \`printf '%s' '<token>' | gcloud secrets versions add wa-token --data-file=-\`,
    then redeploy (deploy.sh) so the new version is mounted.
combiner: OR
conditions:
  - displayName: "send_failed event from ${SERVICE}"
    conditionMatchedLog:
      filter: >-
        ${SVC_FILTER}
        AND textPayload:"\\"event\\": \\"send_failed\\""
notificationChannels:
  - ${CHANNEL}
alertStrategy:
  notificationRateLimit:
    period: 1800s
  autoClose: 1800s
EOF
apply_policy "${POLICY_SEND}" "${TMP}/send.yaml"

# --- 5. No inbound in 6 daytime hours ----------------------------------------
# A log-based counter writes a point only when an `inbound` line appears, so
# absent_over_time() over 6h is true exactly when nothing came in. hour() and
# day_of_week() are UTC: SGT is UTC+8 with no DST. The condition is gated to UTC
# 06:00-12:59 (SGT 14:00-20:59), so the 6-hour window it looks back over always
# lies within 08:00-21:00 SGT, and never on Sunday (day_of_week 0; the gated UTC
# hours fall on the same calendar day in SGT).
echo
echo "==> Inbound-silence alert"
if [[ "${SILENCE_ALERT}" == "1" ]]; then
  INBOUND_FILTER="${SVC_FILTER} AND textPayload:\"\\\"event\\\": \\\"inbound\\\"\""
  if gcloud logging metrics describe "${INBOUND_METRIC}" --project="${PROJECT}" >/dev/null 2>&1; then
    gcloud logging metrics update "${INBOUND_METRIC}" --project="${PROJECT}" \
      --log-filter="${INBOUND_FILTER}" --quiet >/dev/null
    echo "    metric ${INBOUND_METRIC} updated"
  else
    gcloud logging metrics create "${INBOUND_METRIC}" --project="${PROJECT}" \
      --description="Customer messages received by goji-wa-agent (event inbound)" \
      --log-filter="${INBOUND_FILTER}" --quiet >/dev/null
    echo "    metric ${INBOUND_METRIC} created"
  fi
  cat > "${TMP}/silence.yaml" <<EOF
displayName: "${POLICY_SILENCE}"
documentation:
  mimeType: text/markdown
  content: |
    **No customer message has reached goji-wa-agent for 6 hours of clinic
    daytime.** Either it is a genuinely quiet day, or the webhook stopped
    arriving: Meta unsubscribed the app, the provider's forwarding broke, the
    token expired, or signature checks are rejecting everything.

    1. Send the clinic number a WhatsApp from your own phone.
    2. Look for it: \`gcloud run services logs read ${SERVICE} --region ${REGION} --limit 50\`
    3. Meta app > WhatsApp > Configuration: callback URL and the
       **messages** subscription; or the provider's webhook settings.
    4. 401/403 on POST /webhook in the logs: wa-app-secret (or the URL token) is wrong.
combiner: OR
conditions:
  - displayName: "no inbound event in 6h (SGT daytime, Mon-Sat)"
    conditionPrometheusQueryLanguage:
      query: >-
        absent_over_time(logging_googleapis_com:user_${INBOUND_METRIC}[6h])
        and on() (hour() >= 6 and hour() <= 12)
        and on() (day_of_week() != 0)
      duration: 0s
      evaluationInterval: 300s
notificationChannels:
  - ${CHANNEL}
alertStrategy:
  autoClose: 43200s
EOF
  apply_policy "${POLICY_SILENCE}" "${TMP}/silence.yaml"
else
  echo "    skipped (SILENCE_ALERT=0)"
fi

echo
echo "============================================================"
echo " Done. Verify the probe right now:"
echo "   curl -s ${URL}/healthcheck"
echo " Alert policies:"
echo "   https://console.cloud.google.com/monitoring/alerting?project=${PROJECT}"
echo "============================================================"
