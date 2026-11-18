-- marts.wa_agent_events  (+ marts.wa_agent_turns)
--
-- Append-only log of the WhatsApp assistant (goji-wa-agent), one row per thing
-- that happened: a customer message arrived, the agent proposed a reply, the
-- policy sent / drafted / escalated / stayed silent, a person took a chat over
-- (echo from the WhatsApp Business app), a mode changed, a delivery status came
-- back. It is how Phase 0 measures response time and cost, and how we audit
-- every decision the agent made.
--
-- NO MESSAGE TEXT AND NO PHONE NUMBERS. chat_key is a salted hash of the
-- WhatsApp id, so this table can be queried freely; transcripts live only in
-- Firestore under a 30-day TTL. Keep it that way: don't add text columns.
--
-- event: inbound | echo | proposal | sent | drafted | escalated | silent |
--        superseded | send_failed | mode | status | kill_switch
-- Timing columns (all from the service's own clock):
--   webhook_lag_s  customer's send time -> our webhook (Meta/provider delay)
--   agent_ms       the model + tool loop for one message
--   steps_json     [{kind: model|tool, name, ms, error}] per step
--   e2e_ms         our webhook -> our send call returned (includes the
--                  deliberate pre-send hold)
--   status rows    delivered/read timestamps for our sends, joined on wa_msg_id
--
-- Written by wa_agent/events.py (streaming insert); the service account needs
-- table-level dataEditor (deploy_admin.sh grant loop).

CREATE TABLE IF NOT EXISTS `goji-bi.marts.wa_agent_events` (
  event_id           STRING    NOT NULL,
  event              STRING    NOT NULL,
  chat_key           STRING    OPTIONS(description="Salted hash of the WhatsApp id. Not reversible, not a phone number."),
  at                 TIMESTAMP NOT NULL,
  kind               STRING    OPTIONS(description="inbound: text | image | audio | interactive ..."),
  webhook_lag_s      FLOAT64,
  echo_lag_s         FLOAT64,
  reason             STRING,
  mode_from          STRING,
  mode_to            STRING,
  intent             STRING,
  confidence         FLOAT64,
  escalate           BOOL,
  decision           STRING    OPTIONS(description="send | draft | escalate"),
  agent_ms           INT64,
  steps_json         STRING,
  tools              STRING,
  model              STRING    OPTIONS(description="Model that actually served the turn (differs from config on a fallback)"),
  stop               STRING,
  input_tokens       INT64,
  output_tokens      INT64,
  cache_read_tokens  INT64,
  cache_write_tokens INT64,
  cost_usd           FLOAT64   OPTIONS(description="Estimate from list prices in agent.py"),
  wa_msg_id          STRING,
  status             STRING,
  status_ts          FLOAT64,
  e2e_ms             INT64,
  kill_on            BOOL
)
PARTITION BY DATE(at);

-- One row per customer message the agent acted on: decision, timings, cost and
-- when our reply was delivered. The Phase 0 latency/cost readout.
CREATE OR REPLACE VIEW `goji-bi.marts.wa_agent_turns` AS
WITH p AS (
  SELECT chat_key, at, intent, confidence, decision, reason, agent_ms, tools,
         model, cost_usd
  FROM `goji-bi.marts.wa_agent_events` WHERE event = 'proposal'
),
s AS (
  SELECT chat_key, at, event AS outcome, wa_msg_id, e2e_ms
  FROM `goji-bi.marts.wa_agent_events`
  WHERE event IN ('sent', 'escalated', 'drafted', 'superseded', 'send_failed')
),
d AS (
  SELECT wa_msg_id, MIN(IF(status = 'delivered', status_ts, NULL)) AS delivered_ts
  FROM `goji-bi.marts.wa_agent_events` WHERE event = 'status'
  GROUP BY wa_msg_id
)
SELECT
  p.chat_key, p.at AS proposed_at, p.intent, p.confidence, p.decision, p.reason,
  p.agent_ms, p.tools, p.model, p.cost_usd,
  s.outcome, s.e2e_ms,
  TIMESTAMP_DIFF(TIMESTAMP_SECONDS(CAST(d.delivered_ts AS INT64)), s.at, SECOND) AS send_to_delivered_s
FROM p
LEFT JOIN s
  ON s.chat_key = p.chat_key
 AND s.at BETWEEN p.at AND TIMESTAMP_ADD(p.at, INTERVAL 2 MINUTE)
LEFT JOIN d USING (wa_msg_id)
QUALIFY ROW_NUMBER() OVER (PARTITION BY p.chat_key, p.at ORDER BY s.at) = 1;
