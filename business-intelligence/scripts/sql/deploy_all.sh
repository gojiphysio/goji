#!/usr/bin/env bash
#
# Deploy all stg + marts SQL views to BigQuery.
#
# All views are CREATE OR REPLACE, so this is idempotent and safe to re-run
# whenever a .sql file changes. Run stg first, then marts (marts depend on stg).
#
# Usage:
#   ./deploy_all.sh                   # deploy to goji-bi
#   PROJECT=other-project ./deploy_all.sh

set -euo pipefail

PROJECT="${PROJECT:-goji-bi}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

deploy_dir() {
  local dir="$1"
  shopt -s nullglob
  local files=("${HERE}/${dir}"/*.sql)
  shopt -u nullglob
  if [[ ${#files[@]} -eq 0 ]]; then
    echo "  (no .sql files in ${dir}/)"
    return
  fi
  for f in "${files[@]}"; do
    echo "==> $(basename "$f")"
    bq query \
      --project_id="${PROJECT}" \
      --use_legacy_sql=false \
      --quiet \
      < "$f"
  done
}

echo "Deploying stg/ views ..."
deploy_dir stg

echo
echo "Deploying marts/ views ..."
deploy_dir marts

echo
echo "Done. All views are now current against ${PROJECT}."
