#!/usr/bin/env bash
# Fetch fresh Search Console numbers for the SEO loop, keylessly.
#
# Dispatches the "Search Console export" workflow on main, waits for it, and
# downloads its artifact (daily.json, terms.json, meta.json) into DIR.
# Needs only an authenticated `gh`: no gcloud, no Google key.
#
#   marketing/seo/tools/fetch_search_console.sh [DIR]   (default: ./search-console)
set -euo pipefail

dir="${1:-search-console}"
repo="gojiphysio/goji"
wf="search-console-export.yml"

# A minute of slack for clock skew between this machine and GitHub.
since=$(python3 -c 'import datetime as d; print((d.datetime.now(d.timezone.utc) - d.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))')
gh workflow run "$wf" --repo "$repo" --ref main

id=""
for _ in $(seq 1 30); do
  id=$(gh run list --repo "$repo" --workflow "$wf" --event workflow_dispatch --limit 10 \
         --json databaseId,createdAt \
         --jq "[.[] | select(.createdAt >= \"$since\")] | last | .databaseId // empty")
  [[ -n "$id" ]] && break
  sleep 4
done
[[ -n "$id" ]] || { echo "fetch_search_console: the export run did not start" >&2; exit 1; }

if ! gh run watch "$id" --repo "$repo" --exit-status --interval 10 >/dev/null; then
  echo "fetch_search_console: export run $id failed:" >&2
  gh run view "$id" --repo "$repo" --log-failed 2>&1 | tail -20 >&2
  exit 1
fi

rm -rf "$dir"
gh run download "$id" --repo "$repo" --name search-console --dir "$dir"
cat "$dir/meta.json"
