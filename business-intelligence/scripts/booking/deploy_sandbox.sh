#!/usr/bin/env bash
#
# Deploy goji-shop-sandbox: the booking service's shop endpoints in Stripe TEST
# mode, for reviewing the shop on a Cloudflare branch preview. Same code as
# goji-booking, but SHOP_SANDBOX=1: it refuses a live Stripe key and never calls
# Plato, so reviewers can check out with card 4242 4242 4242 4242 and nothing
# reaches clinic data. Preview builds find it via SHOP_SANDBOX_API in the site's
# src/lib/shop.ts.
#
# Secret (create once, from a terminal that has the sk_test_ key):
#   printf '%s' "$STRIPE_API_KEY" | gcloud secrets create stripe-test-key --data-file=-
#   gcloud secrets add-iam-policy-binding stripe-test-key \
#     --member=serviceAccount:dashboard-sa@goji-bi.iam.gserviceaccount.com \
#     --role=roles/secretmanager.secretAccessor
#
# Re-runnable. Scales to zero when unused.

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-goji-shop-sandbox}"
# Origins that may call it: the shop branch preview (stable alias) and local dev.
CORS_ORIGIN="${CORS_ORIGIN:-https://claude-website-shop-feasibil.goji-bgb.pages.dev,http://localhost:4234}"
SA="dashboard-sa@${PROJECT}.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" --region="${REGION}" --source="${HERE}" \
  --service-account="${SA}" \
  --set-env-vars="^|^GCP_PROJECT=${PROJECT}|CORS_ORIGIN=${CORS_ORIGIN}|SHOP_SANDBOX=1|SHOP_PLATO_DRY_RUN=1|SHOP_PLATO_DOCTOR=SHP" \
  --set-secrets="STRIPE_API_KEY=stripe-test-key:latest" \
  --max-instances=1 --min-instances=0 \
  --allow-unauthenticated \
  --quiet

gcloud run services describe "${SERVICE}" --project="${PROJECT}" --region="${REGION}" --format='value(status.url)'
