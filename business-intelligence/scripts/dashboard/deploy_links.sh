#!/usr/bin/env bash
#
# Stand up the public click-to-WhatsApp redirector as its OWN Cloud Run service
# + subdomain:
#   https://go.gojiphysio.com/<slug>     (e.g. /ig, /web, /gbp, /ads, /email, /qr)
#
# Same container image as the dashboard, but launched with APP_MODE=links so it:
#   - serves the slug redirect at the ROOT (go.gojiphysio.com/ig)
#   - logs each click to marts.link_click_events, then 302s to a wa.me deep link
#   - returns 404 on every dashboard/front-desk route — the internal tool does
#     NOT exist on this public domain.
#
# Why a separate subdomain: the founder dashboard (dashboard.gojiphysio.com) is
# an internal tool and shouldn't be the URL we publish in Instagram bios, GBP,
# ads, or on printed QR codes. This gives a short, on-brand public link while
# keeping the dashboard internal.
#
# Run from Google Cloud Shell, with the WhatsApp number exported:
#   WHATSAPP_NUMBER=6580000000 bash business-intelligence/scripts/dashboard/deploy_links.sh
#
# Re-runnable. Does NOT touch goji-dashboard or goji-frontdesk.

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-links}"
DOMAIN="${DOMAIN:-go.gojiphysio.com}"
SA="dashboard-sa@${PROJECT}.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Public-link config. WHATSAPP_NUMBER is E.164 digits, no '+'. If unset, the
# redirect falls back to the site (links never dead-end) — but you'll want it
# set for the links to actually open WhatsApp.
WHATSAPP_NUMBER="${WHATSAPP_NUMBER:-}"
WHATSAPP_FALLBACK_URL="${WHATSAPP_FALLBACK_URL:-https://www.gojiphysio.com}"

echo "============================================================"
echo " Goji — publishing the click-to-WhatsApp redirector"
echo " Project: ${PROJECT}   Region: ${REGION}   Service: ${SERVICE}"
echo " WhatsApp number: ${WHATSAPP_NUMBER:-<unset — links fall back to site>}"
echo "============================================================"
gcloud config set project "${PROJECT}" >/dev/null

# --- Deploy the links service -----------------------------------------------
# No --set-secrets: links mode has no authenticated routes, so it needs no
# dashboard/staff credentials. It still runs as dashboard-sa so it can append
# clicks to marts.link_click_events (table-level dataEditor grant).
echo
echo "==> Deploying ${SERVICE} (APP_MODE=links)"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --set-env-vars=GCP_PROJECT=${PROJECT},CACHE_TTL_SECONDS=300,APP_MODE=links,WHATSAPP_NUMBER=${WHATSAPP_NUMBER},WHATSAPP_FALLBACK_URL=${WHATSAPP_FALLBACK_URL} \
  --allow-unauthenticated \
  --quiet

# --- Map the subdomain ------------------------------------------------------
echo
echo "==> Mapping ${DOMAIN} -> ${SERVICE}"
if gcloud beta run domain-mappings describe --domain="${DOMAIN}" \
     --region="${REGION}" --project="${PROJECT}" >/dev/null 2>&1; then
  echo "    domain mapping already exists"
else
  gcloud beta run domain-mappings create --service="${SERVICE}" \
    --domain="${DOMAIN}" --region="${REGION}" --project="${PROJECT}"
  echo
  echo "    >> Add this DNS record on the gojiphysio.com zone:"
  echo "         go  CNAME  ghs.googlehosted.com."
  echo "       (TLS cert auto-provisions once the CNAME resolves.)"
fi

echo
echo "============================================================"
echo " Done — public links live at:"
echo "   https://${DOMAIN}/ig    (Instagram bio)"
echo "   https://${DOMAIN}/web   (website button)"
echo "   https://${DOMAIN}/gbp   (Google Business Profile)"
echo "   https://${DOMAIN}/ads   https://${DOMAIN}/email   https://${DOMAIN}/qr"
echo " Each logs a click then opens WhatsApp. Slugs/messages live in"
echo " LINK_SLUGS in app.py."
echo "============================================================"
