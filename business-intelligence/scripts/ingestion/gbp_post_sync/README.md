# gbp_post_sync — Instagram posts → Google Business Profile posts

Cloud Run Job, daily. Reads new Instagram posts (Meta Graph API, same token as
`marketing_ingest`) and creates one GBP post per IG post
(`localPosts.create`, Business Profile API v4), so the profile's Updates stay
at Instagram's cadence without anyone posting twice.

- Caption → post text: URLs, SG phone numbers (GBP rejects posts with them),
  "link in bio" lines and the trailing hashtag block are stripped; trimmed to
  1,500 chars.
- Image: the photo, a reel's cover frame, or a carousel's first slide.
- Button: **Book** → `https://go.gojiphysio.com/gbp-post-book` (logs as
  "Google post", separate from the profile's own `gbp-book`).
- Only IG posts from the last 3 days, at most 2 GBP posts per run, oldest
  first. Captions matching `GBP_SKIP_PATTERN` (regex) are skipped.
- Ledger: `raw_marketing.gbp_post_sync_raw`. Anything `posted` or `skipped`
  is never touched again, so re-runs can't double-post.

## Dry run (default)

`GBP_DRY_RUN=true` reads Instagram and writes `dry_run` rows with the exact
post body it would send. It needs no GBP access, so it runs before Google's
API approval. Review what it would have posted:

```sql
SELECT ig_timestamp, ig_permalink, reason,
       JSON_VALUE(payload, '$.summary') AS summary,
       JSON_VALUE(payload, '$.media[0].sourceUrl') AS image
FROM `goji-bi.raw_marketing.gbp_post_sync_raw`
WHERE status = 'dry_run'
QUALIFY ROW_NUMBER() OVER (PARTITION BY ig_media_id ORDER BY _loaded_at DESC) = 1
ORDER BY ig_timestamp DESC
```

## One-time setup

1. **Ledger table** (once):
   ```bash
   bq --project_id=goji-bi --location=asia-southeast1 \
     query --use_legacy_sql=false < scripts/ingestion/gbp_post_sync/schema.sql
   ```
2. **Deploy** happens in CI on merge (dry run, as soon as `IG_USER_ID` is set).
3. **Schedule** (once; 19:00 SGT, after the day's IG posts):
   ```bash
   gcloud scheduler jobs create http gbp-post-sync-daily \
     --location asia-southeast1 \
     --schedule "0 19 * * *" \
     --time-zone "Asia/Singapore" \
     --uri "https://run.googleapis.com/v2/projects/goji-bi/locations/asia-southeast1/jobs/gbp-post-sync:run" \
     --http-method POST \
     --oauth-service-account-email "scheduler-sa@goji-bi.iam.gserviceaccount.com"
   ```

## Going live (after Google approves API access)

Access is requested once through Google's Business Profile API form with the
goji-bi project number; quota on the APIs page goes from 0 to 300/min when
approved. Then, signed in as **hello@gojiphysio.com**:

1. Enable the APIs:
   ```bash
   gcloud services enable mybusiness.googleapis.com \
     mybusinessaccountmanagement.googleapis.com \
     mybusinessbusinessinformation.googleapis.com --project=goji-bi
   ```
2. Create an OAuth client (Console → APIs & Services → Credentials → OAuth
   client ID → **Desktop app**), download it as `client.json`, then mint the
   token. GBP has no service-account path; posts are made as hello@.
   ```bash
   gcloud auth application-default login \
     --client-id-file=client.json \
     --scopes=https://www.googleapis.com/auth/business.manage
   ```
3. Find the location (`accounts/<id>/locations/<id>`):
   ```bash
   T=$(gcloud auth application-default print-access-token)
   curl -s -H "Authorization: Bearer $T" \
     https://mybusinessaccountmanagement.googleapis.com/v1/accounts
   curl -s -H "Authorization: Bearer $T" \
     "https://mybusinessbusinessinformation.googleapis.com/v1/accounts/<id>/locations?readMask=name,title"
   ```
4. Store the token and grant the job's SA:
   ```bash
   gcloud secrets create gbp-oauth --project=goji-bi \
     --data-file="$HOME/.config/gcloud/application_default_credentials.json"
   gcloud secrets add-iam-policy-binding gbp-oauth --project=goji-bi \
     --member="serviceAccount:ingestion-sa@goji-bi.iam.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor"
   ```
   That file is now hello@'s GBP credential: delete it locally or re-run
   `gcloud auth application-default login` as normal afterwards.
5. Set repo vars `GBP_LOCATION=accounts/<id>/locations/<id>` and
   `GBP_LIVE=true`, then re-run the deploy workflow. Both are required; either
   alone stays in dry run.

## Env vars

| Var | Default | Notes |
|---|---|---|
| `IG_USER_ID` / `META_GRAPH_TOKEN` | — | same as marketing_ingest (token is a secret) |
| `GBP_DRY_RUN` | `true` | `false` only via the live deploy branch |
| `GBP_LOCATION` | — | required when live |
| `GBP_OAUTH_JSON` | — | secret `gbp-oauth`; required when live |
| `GBP_CTA_URL` | `https://go.gojiphysio.com/gbp-post-book` | |
| `GBP_LOOKBACK_DAYS` | `3` | |
| `GBP_MAX_POSTS` | `2` | per run |
| `GBP_SKIP_PATTERN` | — | case-insensitive regex on the raw caption |

Exit codes: 0 ok / 1 config / 2 BQ / 3 API (any post rejected; it is ledgered
`error` and retried next run).
