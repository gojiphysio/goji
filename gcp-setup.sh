#!/usr/bin/env bash
#
# Goji BI - GCP setup for Claude Desktop MCP access
#
# Grants BigQuery read access to your wife's Google account so she can query
# the curated dataset via Claude Desktop using Application Default Credentials.
#
# This approach avoids service account key files (blocked by the
# iam.disableServiceAccountKeyCreation org policy) and is the recommended
# architecture for a small team.
#
# Usage:
#   1. Edit the CONFIG block below. WIFE_EMAIL must be set.
#   2. Make sure gcloud is logged in and set to the right project:
#        gcloud auth login
#        gcloud config set project goji-bi
#   3. Run: bash gcp-setup.sh
#
# Cost guardrails (daily quota + budget alert) are Console-only and printed
# as next steps at the end.

set -euo pipefail

# ---- CONFIG (edit before running) -------------------------------------------
PROJECT_ID="goji-bi"
WIFE_EMAILS=("hello@gojiphysio.com")        # add more emails to the array if needed
DATASET="marts"                             # curated dataset (currently has fct_invoice_line, fct_service_delivered)
# -----------------------------------------------------------------------------

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
warn()  { printf "\033[33m   %s\033[0m\n" "$*"; }
ok()    { printf "\033[32m   %s\033[0m\n" "$*"; }
fail()  { printf "\033[31m   %s\033[0m\n" "$*"; exit 1; }

if [[ ${#WIFE_EMAILS[@]} -eq 0 ]]; then
  fail "Edit the script and add at least one email to the WIFE_EMAILS array."
fi

bold "==> Checking gcloud project is set to ${PROJECT_ID}"
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [[ "${CURRENT_PROJECT}" != "${PROJECT_ID}" ]]; then
  fail "gcloud is on '${CURRENT_PROJECT}', expected '${PROJECT_ID}'. Run: gcloud config set project ${PROJECT_ID}"
fi
ok "OK"

DATASET_EXISTS=true
if ! bq show --project_id="${PROJECT_ID}" "${DATASET}" >/dev/null 2>&1; then
  DATASET_EXISTS=false
  warn "Dataset '${DATASET}' does not exist yet. Dataset-level grants will be skipped."
  warn "Re-run after ${DATASET} is created, or edit DATASET to the curated dataset of today."
fi

for EMAIL in "${WIFE_EMAILS[@]}"; do
  bold "==> Granting bigquery.jobUser to ${EMAIL} at project level"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="user:${EMAIL}" \
    --role="roles/bigquery.jobUser" \
    --condition=None \
    --quiet >/dev/null
  ok "Granted (or already present)."

  if [[ "${DATASET_EXISTS}" == "true" ]]; then
    bold "==> Granting bigquery.dataViewer on dataset ${DATASET} to ${EMAIL}"
    if bq add-iam-policy-binding \
        --member="user:${EMAIL}" \
        --role="roles/bigquery.dataViewer" \
        "${PROJECT_ID}:${DATASET}" >/dev/null 2>&1; then
      ok "Granted via bq add-iam-policy-binding."
    else
      warn "bq add-iam-policy-binding failed (older bq version?)."
      warn "Falling back to dataset ACL merge."
      TMP=$(mktemp)
      bq show --format=prettyjson "${PROJECT_ID}:${DATASET}" > "${TMP}"
      python3 - "${TMP}" "${EMAIL}" <<'PY'
import json, sys
path, email = sys.argv[1], sys.argv[2]
with open(path) as f:
    d = json.load(f)
acc = d.get('access', [])
entry = {'role': 'READER', 'userByEmail': email}
if entry not in acc:
    acc.append(entry)
    d['access'] = acc
    with open(path, 'w') as f:
        json.dump(d, f)
PY
      bq update --source "${TMP}" "${PROJECT_ID}:${DATASET}" >/dev/null
      rm "${TMP}"
      ok "Granted via dataset ACL merge."
    fi
  fi
done

PRINTED_EMAILS=$(printf "%s, " "${WIFE_EMAILS[@]}"); PRINTED_EMAILS=${PRINTED_EMAILS%, }

cat <<EOF

==============================================================================
DONE - ${PRINTED_EMAILS} now have read-only BigQuery access.

  Identities:       ${PRINTED_EMAILS}
  Project:          ${PROJECT_ID}
  Dataset access:   ${DATASET} (read-only)
  Job runner:       yes (project-level)

NEXT STEPS:

  1. On HER machine, she runs ONCE (signed in as whichever Google account
     she'll use day-to-day, most likely hello@gojiphysio.com):
       gcloud auth application-default login
     This writes ADC credentials to
     ~/.config/gcloud/application_default_credentials.json that Claude
     Desktop's MCP server will use automatically.

  2. Set the cost guardrails (Console, ~1 min each):

     Daily query quota
     https://console.cloud.google.com/iam-admin/quotas?project=${PROJECT_ID}
     Filter "BigQuery API" -> "Query usage per day" -> 10 GiB/day.

     Budget alert
     https://console.cloud.google.com/billing/budgets
     Scope this project + BigQuery service, \$5/month, alerts at 50/90/100%.

  3. Continue with Part 2 of wife-claude-setup-guide.md on her machine.

==============================================================================
EOF
