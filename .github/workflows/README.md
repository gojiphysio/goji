# CI / auto-deploy

`deploy-dashboard.yml` runs the test suites and then deploys the dashboard
(and, when they change, the SQL views and the patients ingest job) to Cloud Run
on every push to `main`. Google Cloud auth uses **Workload Identity Federation**
— GitHub proves its identity to GCP with a short-lived token, so **no
service-account key is ever stored** in the repo or anywhere else.

## One-time setup (needs a project Owner; ~5 minutes)

Run this once in Cloud Shell. It creates a deploy bot identity, lets *only this
repo* impersonate it, and prints the value to paste into GitHub.

```bash
PROJECT=goji-bi
REGION=asia-southeast1
REPO=gojiphysio/goji            # owner/repo
POOL=github-pool
PROVIDER=github-provider
DEPLOYER="github-deployer@${PROJECT}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT"

# 1. Deploy bot service account + the permissions a deploy needs.
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions deployer" || true
# Wait for the new account to propagate before granting roles, otherwise the
# first few bindings can fail with "Service account does not exist".
until gcloud iam service-accounts describe "$DEPLOYER" >/dev/null 2>&1; do
  echo "  waiting for ${DEPLOYER} to propagate…"; sleep 3
done
for ROLE in \
  roles/run.admin \
  roles/iam.serviceAccountUser \
  roles/cloudbuild.builds.editor \
  roles/artifactregistry.writer \
  roles/storage.admin \
  roles/bigquery.admin ; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${DEPLOYER}" --role="$ROLE" --condition=None >/dev/null
done

# 2. Workload Identity pool + a provider locked to GitHub's OIDC issuer,
#    and an attribute condition so ONLY this repo can authenticate.
gcloud iam workload-identity-pools create "$POOL" \
  --location=global --display-name="GitHub" || true
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --location=global --workload-identity-pool="$POOL" \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${REPO}'" || true

# 3. Let that repo impersonate the deploy bot.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${REPO}"

# 4. Print the values to paste into GitHub.
echo
echo "Set these as GitHub repo VARIABLES (Settings > Secrets and variables > Actions > Variables):"
echo "  GCP_PROJECT            = ${PROJECT}"
echo "  GCP_REGION             = ${REGION}"
echo "  DEPLOY_SERVICE_ACCOUNT = ${DEPLOYER}"
echo "  WIF_PROVIDER           = projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"
```

Then, on GitHub: **Settings → Secrets and variables → Actions → Variables → New
repository variable** and add the four `GCP_PROJECT` / `GCP_REGION` /
`DEPLOY_SERVICE_ACCOUNT` / `WIF_PROVIDER` values printed above.

## Prerequisites that already exist (from the manual deploy)

These are created once by `deploy_admin.sh` and reused by CI — they are **not**
recreated here:

- Secrets `dashboard-user`, `dashboard-pass`, `dashboard-staff-user`,
  `dashboard-staff-pass`, `plato-api-key`.
- Service accounts `dashboard-sa` (dashboard runtime) and `ingestion-sa`
  (patients job runtime).

So: run `deploy_admin.sh` once to bootstrap, do the setup above, and from then
on every push to `main` deploys automatically.

## After setup

- Push to `main` → **Actions** tab shows tests → deploy.
- Trigger manually anytime: **Actions → Deploy dashboard → Run workflow**.
- The deploy bot's roles are broad (it's a deploy pipeline); tighten later when
  the team/permissions model grows.
