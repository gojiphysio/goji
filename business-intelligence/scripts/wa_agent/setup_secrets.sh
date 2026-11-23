#!/usr/bin/env bash
#
# One-time: create the WhatsApp assistant's secrets in Secret Manager.
# Run as a project owner (Charles) in Cloud Shell, from the repo root:
#   bash business-intelligence/scripts/wa_agent/setup_secrets.sh
#   USE_URL_TOKEN=1 bash ...    # provider without Meta's signature (Track B)
#   REMINDERS_WA=1  bash ...    # also let the reminders job (dashboard-sa) read wa-token
#
# Idempotent: an existing secret is left exactly as it is (never overwritten,
# never given a new version), so re-running is safe. To change a vendor value
# later, add a version by hand:
#   printf '%s' '<value>' | gcloud secrets versions add <name> --data-file=- --project goji-bi
#
# Tokens we own are generated (openssl rand -hex 32). Vendor values are typed at
# a hidden prompt. Values travel by pipe, never as a command-line argument, and
# nothing is echoed except the two you need to type elsewhere: the verify token
# (Meta's webhook form) and the admin token (X-Admin-Token for the /admin
# routes). Those are printed once, at the end. Read any value back later with
#   gcloud secrets versions access latest --secret=<name> --project goji-bi
#
# Existence is checked with `gcloud secrets describe`, which works for an owner.
# Don't copy that check into CI: the GitHub deployer SA has no Secret Manager
# role, so the same call fails whether or not the secret exists (see
# deploy-booking.yml and deploy-dashboard.yml).

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
BOOKING_SA="dashboard-sa@${PROJECT}.iam.gserviceaccount.com"   # goji-booking's runtime SA

gcloud config set project "${PROJECT}" >/dev/null
gcloud services enable secretmanager.googleapis.com --project="${PROJECT}" --quiet
command -v openssl >/dev/null || { echo "!! openssl is needed to generate tokens"; exit 1; }

PRINT_VERIFY=""
PRINT_ADMIN=""

# 0 = exists, 1 = missing. Anything else (no permission, wrong project) stops
# the script rather than being read as "missing".
secret_exists() {
  local out
  if out="$(gcloud secrets describe "$1" --project="${PROJECT}" 2>&1 >/dev/null)"; then
    return 0
  fi
  if grep -qiE "NOT_FOUND|not found" <<<"${out}"; then
    return 1
  fi
  echo "!! could not check secret $1:" >&2
  echo "${out}" >&2
  exit 1
}

create_from_stdin() {  # name; value on stdin
  gcloud secrets create "$1" --project="${PROJECT}" --replication-policy=automatic \
    --data-file=- --quiet >/dev/null
}

prompt_secret() {  # name, what to paste
  local name="$1" what="$2" value=""
  if secret_exists "${name}"; then
    echo "  ${name}: exists, left as is"
    return
  fi
  while [[ -z "${value}" ]]; do
    read -r -s -p "  ${name}: paste ${what} (hidden), then Enter: " value
    echo
  done
  printf '%s' "${value}" | create_from_stdin "${name}"
  unset value
  echo "  ${name}: created"
}

random_secret() {  # name [print-var]
  local name="$1" keep="${2:-}" value
  if secret_exists "${name}"; then
    echo "  ${name}: exists, left as is"
    return
  fi
  value="$(openssl rand -hex 32)"
  printf '%s' "${value}" | create_from_stdin "${name}"
  if [[ -n "${keep}" ]]; then printf -v "${keep}" '%s' "${value}"; fi
  unset value
  echo "  ${name}: created (random)"
}

echo "==> Vendor values"
prompt_secret anthropic-api-key  "the Claude API key (Goji workspace, console.anthropic.com)"
prompt_secret wa-token           "the Meta system-user token (or the provider's API key)"
prompt_secret wa-app-secret      "the Meta app secret (App settings > Basic)"

echo "==> Generated tokens"
random_secret wa-verify-token          PRINT_VERIFY
random_secret wa-agent-admin-token     PRINT_ADMIN
random_secret wa-agent-internal-token
random_secret wa-agent-feedback-secret
if secret_exists wa-agent-hash-salt; then
  echo "  wa-agent-hash-salt: exists, left as is"
else
  random_secret wa-agent-hash-salt
  cat <<'EOF'
  !! wa-agent-hash-salt: NEVER rotate or delete it. It keys chat_key in
     marts.wa_agent_events (the salted hash that stands in for the phone
     number), so a new salt splits every chat's history in two and breaks the
     learning loop's joins. Rows written before this secret existed used the
     built-in default salt and won't join to rows written after.
EOF
fi
if [[ "${USE_URL_TOKEN:-0}" == "1" ]]; then
  random_secret wa-webhook-url-token
  echo "     The provider's webhook URL is <service url>/webhook/<token>; read the token with"
  echo "     gcloud secrets versions access latest --secret=wa-webhook-url-token --project ${PROJECT}"
fi

echo "==> Existing secrets the service also mounts"
if secret_exists gmail-app-password; then
  echo "  gmail-app-password: exists"
else
  echo "  !! gmail-app-password is missing; escalation emails need it (see booking/README.md)"
fi

echo "==> Grants"
# goji-booking (runs as dashboard-sa) sends the internal token on /internal/book
# and the booking-confirmed callback. The assistant's own SA gets its grants
# from deploy.sh, which also creates that SA.
gcloud secrets add-iam-policy-binding wa-agent-internal-token --project="${PROJECT}" \
  --member="serviceAccount:${BOOKING_SA}" --role=roles/secretmanager.secretAccessor \
  --quiet >/dev/null
echo "  ${BOOKING_SA} can read wa-agent-internal-token"
if [[ "${REMINDERS_WA:-0}" == "1" ]]; then
  # The appointment-reminders job also runs as dashboard-sa (reminders/README.md,
  # "Turning on WhatsApp", step 3).
  gcloud secrets add-iam-policy-binding wa-token --project="${PROJECT}" \
    --member="serviceAccount:${BOOKING_SA}" --role=roles/secretmanager.secretAccessor \
    --quiet >/dev/null
  echo "  ${BOOKING_SA} can read wa-token (reminders job)"
fi

echo
echo "==> Done."
if [[ -n "${PRINT_VERIFY}" || -n "${PRINT_ADMIN}" ]]; then
  echo "    Shown once. Copy them now (re-read later with gcloud secrets versions access):"
  if [[ -n "${PRINT_VERIFY}" ]]; then
    echo "    wa-verify-token       ${PRINT_VERIFY}"
    echo "        -> Meta app > WhatsApp > Configuration > Webhook > Verify token"
  fi
  if [[ -n "${PRINT_ADMIN}" ]]; then
    echo "    wa-agent-admin-token  ${PRINT_ADMIN}"
    echo "        -> X-Admin-Token header for the /admin routes; keep it in a password manager"
  fi
fi
echo "    Next: deploy (see the Runbook in business-intelligence/scripts/wa_agent/README.md)."
