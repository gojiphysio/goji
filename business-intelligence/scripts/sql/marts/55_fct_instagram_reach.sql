-- marts.fct_instagram_reach
--
-- Thin fact: one row per date carrying that day's rolling 28-day Instagram
-- reach reading (Meta's de-duplicated reach over the trailing 28 days).
--
-- Reach is NOT additive — it counts unique accounts, so monthly reach is not
-- the sum of daily reach. Consumers read the LATEST row in their window (reach
-- "as of" the period end), never SUM(reach). The dashboard's fetch_instagram_reach
-- does exactly that.

CREATE OR REPLACE VIEW `goji-bi.marts.fct_instagram_reach` AS
SELECT
  metric_date,
  value AS reach
FROM `goji-bi.stg.instagram`
WHERE metric = 'reach_days_28';
