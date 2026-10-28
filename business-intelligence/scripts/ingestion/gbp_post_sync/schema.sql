-- raw_marketing.gbp_post_sync_raw: append-only ledger for the gbp_post_sync
-- job (Instagram post -> Google Business Profile post). Run once before the
-- first deploy; the job reads it on every run and exits 2 if it is missing.
--
-- One row per decision. status:
--   'posted'  GBP accepted the post (gbp_post_name set). Final.
--   'skipped' deliberately not posted (reason: no_caption / skip_pattern /
--             no_image). Final.
--   'dry_run' what a live run would have done. Not final; repeats daily.
--   'error'   GBP rejected it (reason: http_<code>). Retried next run.
-- The job treats any ig_media_id with a 'posted' or 'skipped' row as done.

CREATE TABLE IF NOT EXISTS `goji-bi.raw_marketing.gbp_post_sync_raw` (
  _loaded_at TIMESTAMP NOT NULL
    OPTIONS(description = "UTC timestamp this row was loaded"),
  ig_media_id STRING NOT NULL
    OPTIONS(description = "Instagram media id the decision is about"),
  ig_permalink STRING
    OPTIONS(description = "Instagram post URL, for review"),
  ig_timestamp TIMESTAMP
    OPTIONS(description = "When the post went up on Instagram"),
  status STRING NOT NULL
    OPTIONS(description = "posted / skipped / dry_run / error"),
  reason STRING
    OPTIONS(description = "Why it was skipped or failed"),
  gbp_post_name STRING
    OPTIONS(description = "GBP resource name of the created post (posted only)"),
  payload JSON
    OPTIONS(description = "The localPosts.create body sent (or that would be sent)")
)
PARTITION BY DATE(_loaded_at)
CLUSTER BY status, ig_media_id
OPTIONS(
  description = "Ledger for the IG -> GBP post sync job. Append-only."
);
