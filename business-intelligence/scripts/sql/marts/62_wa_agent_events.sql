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
  `at`                 TIMESTAMP NOT NULL,
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
PARTITION BY DATE(`at`);

-- One row per customer message the agent acted on: decision, timings, cost and
-- when our reply was delivered. The Phase 0 latency/cost readout.
CREATE OR REPLACE VIEW `goji-bi.marts.wa_agent_turns` AS
WITH p AS (
  SELECT chat_key, `at`, intent, confidence, decision, reason, agent_ms, tools,
         model, cost_usd
  FROM `goji-bi.marts.wa_agent_events` WHERE event = 'proposal'
),
s AS (
  SELECT chat_key, `at`, event AS outcome, wa_msg_id, e2e_ms
  FROM `goji-bi.marts.wa_agent_events`
  WHERE event IN ('sent', 'escalated', 'drafted', 'superseded', 'send_failed')
),
d AS (
  SELECT wa_msg_id, MIN(IF(status = 'delivered', status_ts, NULL)) AS delivered_ts
  FROM `goji-bi.marts.wa_agent_events` WHERE event = 'status'
  GROUP BY wa_msg_id
)
SELECT
  p.chat_key, p.`at` AS proposed_at, p.intent, p.confidence, p.decision, p.reason,
  p.agent_ms, p.tools, p.model, p.cost_usd,
  s.outcome, s.e2e_ms,
  TIMESTAMP_DIFF(TIMESTAMP_SECONDS(CAST(d.delivered_ts AS INT64)), s.`at`, SECOND) AS send_to_delivered_s
FROM p
LEFT JOIN s
  ON s.chat_key = p.chat_key
 AND s.`at` BETWEEN p.`at` AND TIMESTAMP_ADD(p.`at`, INTERVAL 2 MINUTE)
LEFT JOIN d USING (wa_msg_id)
QUALIFY ROW_NUMBER() OVER (PARTITION BY p.chat_key, p.`at` ORDER BY s.`at`) = 1;

-- --- Learning signals (wa_agent/learning.py) ----------------------------------
-- Labels only, never text: how Chris's reply compared with the agent's draft,
-- whether she stepped into a chat the agent was handling, her one-tap rating.
ALTER TABLE `goji-bi.marts.wa_agent_events`
  ADD COLUMN IF NOT EXISTS draft_similarity FLOAT64 OPTIONS(description="echo: 0-1 similarity of Chris's reply to the agent's pending draft"),
  ADD COLUMN IF NOT EXISTS draft_outcome    STRING  OPTIONS(description="echo: sent_unchanged | edited | replaced"),
  ADD COLUMN IF NOT EXISTS rescue           BOOL    OPTIONS(description="echo: Chris wrote in a chat the agent was answering on its own"),
  ADD COLUMN IF NOT EXISTS rating           STRING  OPTIONS(description="feedback: up | down, from the staff email");

-- The wa-book go-link carries ?ref=<chat_key>; the links service logs it so a
-- booking can be credited to the conversation. Also added by
-- 51_link_click_events.sql; repeated here so this file deploys on its own.
ALTER TABLE `goji-bi.marts.link_click_events`
  ADD COLUMN IF NOT EXISTS chat_ref STRING OPTIONS(description="wa-book only: the assistant chat's salted hash (wa_agent_events.chat_key). Not a phone number.");

-- One row per conversation: a chat's messages from a customer message after
-- 24h of quiet until the next such message. Scored for the learning loop:
--   success       booked (via the agent's link) | resolved (agent answered, no person needed)
--   neutral       handover (policy escalation) | draft_sent (Chris sent the draft unchanged)
--   failure       rescued | draft_edited | asked_for_human | unanswered (draft, nobody replied)
--   soft_failure  dropped (agent gave times/link, no booking)
--   open          still live (< 48h since last activity), unless already booked/handed over
CREATE OR REPLACE VIEW `goji-bi.marts.wa_agent_conversations` AS
WITH ev AS (
  SELECT * FROM `goji-bi.marts.wa_agent_events`
  WHERE chat_key IS NOT NULL
    AND event IN ('inbound', 'proposal', 'sent', 'drafted', 'escalated', 'echo', 'feedback')
),
inb AS (
  SELECT chat_key, `at`, LAG(`at`) OVER (PARTITION BY chat_key ORDER BY `at`) AS prev_at
  FROM ev WHERE event = 'inbound'
),
convs AS (
  SELECT chat_key, `at` AS conversation_start,
         LEAD(`at`) OVER (PARTITION BY chat_key ORDER BY `at`) AS next_start
  FROM inb
  WHERE prev_at IS NULL OR TIMESTAMP_DIFF(`at`, prev_at, HOUR) >= 24
),
tagged AS (
  SELECT c.conversation_start, e.*
  FROM convs c
  JOIN ev e
    ON e.chat_key = c.chat_key AND e.`at` >= c.conversation_start
   AND (c.next_start IS NULL OR e.`at` < c.next_start)
),
agg AS (
  SELECT
    chat_key, conversation_start,
    MAX(IF(event != 'feedback', `at`, NULL)) AS last_activity,
    ARRAY_AGG(IF(event = 'proposal', intent, NULL) IGNORE NULLS ORDER BY `at` LIMIT 1)[SAFE_OFFSET(0)] AS first_intent,
    COUNTIF(event = 'inbound')   AS customer_msgs,
    COUNTIF(event = 'sent')      AS auto_sent,
    COUNTIF(event = 'drafted')   AS drafted,
    COUNTIF(event = 'escalated') AS escalated,
    COUNTIF(event = 'echo')      AS staff_msgs,
    IFNULL(SUM(IF(event = 'proposal', cost_usd, NULL)), 0) AS cost_usd,
    MIN(IF(event = 'inbound', `at`, NULL)) AS first_customer_at,
    MIN(IF(event IN ('sent', 'escalated'), `at`, NULL)) AS first_agent_send_at,
    MIN(IF(event = 'sent', `at`, NULL)) AS first_auto_at,
    MIN(IF(event = 'echo', `at`, NULL)) AS first_echo_at,
    LOGICAL_OR(event = 'echo' AND IFNULL(rescue, FALSE)) AS rescued,
    ARRAY_AGG(IF(event = 'echo', draft_outcome, NULL) IGNORE NULLS ORDER BY `at` LIMIT 1)[SAFE_OFFSET(0)] AS draft_outcome,
    MIN(IF(event = 'proposal' AND intent = 'human_requested', `at`, NULL)) AS asked_for_human_at,
    LOGICAL_OR(event = 'proposal' AND decision = 'send'
               AND STRPOS(IFNULL(tools, ''), 'booking_link') > 0) AS gave_link,
    ARRAY_AGG(IF(event = 'feedback', rating, NULL) IGNORE NULLS ORDER BY `at` DESC LIMIT 1)[SAFE_OFFSET(0)] AS rating
  FROM tagged
  GROUP BY chat_key, conversation_start
),
bookings AS (
  -- wa-book click (carrying the chat's ref) -> /book?cid= -> that session's confirmed booking
  SELECT l.chat_ref AS chat_key, MIN(c.occurred_at) AS booked_at
  FROM `goji-bi.marts.link_click_events` l
  JOIN `goji-bi.marts.booking_funnel_events` s ON s.go_click_id = l.click_id
  JOIN `goji-bi.marts.booking_funnel_events` c ON c.session_id = s.session_id AND c.stage = 'confirmed'
  WHERE l.slug = 'wa-book' AND l.chat_ref IS NOT NULL
  GROUP BY l.chat_ref, s.session_id
  UNION ALL
  -- booked in the chat by the agent, or confirmed back by goji-booking (not dry runs)
  SELECT chat_key, `at` FROM `goji-bi.marts.wa_agent_events`
  WHERE event = 'booked' AND NOT STARTS_WITH(IFNULL(reason, ''), 'dry_run')
),
booked AS (
  SELECT a.chat_key, a.conversation_start, MIN(b.booked_at) AS booked_at
  FROM agg a
  JOIN bookings b
    ON b.chat_key = a.chat_key
   AND b.booked_at BETWEEN a.conversation_start AND TIMESTAMP_ADD(a.last_activity, INTERVAL 7 DAY)
  GROUP BY a.chat_key, a.conversation_start
),
scored AS (
  SELECT a.*, bk.booked_at
  FROM agg a LEFT JOIN booked bk USING (chat_key, conversation_start)
)
SELECT
  chat_key, conversation_start, last_activity, first_intent,
  customer_msgs, auto_sent, drafted, escalated, staff_msgs, cost_usd,
  TIMESTAMP_DIFF(first_agent_send_at, first_customer_at, MILLISECOND) / 1000 AS first_reply_s,
  booked_at IS NOT NULL AS booked, booked_at,
  outcome,
  CASE
    WHEN outcome IN ('booked', 'resolved') THEN 'success'
    WHEN outcome IN ('handover', 'draft_sent') THEN 'neutral'
    WHEN outcome = 'dropped' THEN 'soft_failure'
    WHEN outcome = 'open' THEN 'open'
    ELSE 'failure'
  END AS score,
  rating,
  CASE
    WHEN staff_msgs = 0 AND (auto_sent + drafted + escalated) > 0 THEN 'agent'
    WHEN staff_msgs > 0 AND (auto_sent + drafted + escalated) > 0 THEN 'agent_then_human'
    ELSE 'human'
  END AS handled_by
FROM (
  SELECT s.*,
    CASE
      WHEN rescued THEN 'rescued'
      WHEN draft_outcome IN ('edited', 'replaced') THEN 'draft_edited'
      WHEN asked_for_human_at > first_auto_at THEN 'asked_for_human'
      WHEN booked_at IS NOT NULL THEN 'booked'
      WHEN escalated > 0 OR (auto_sent + drafted) = 0 THEN 'handover'
      WHEN draft_outcome = 'sent_unchanged' THEN 'draft_sent'
      WHEN TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), last_activity, HOUR) < 48 THEN 'open'
      WHEN drafted > 0 AND staff_msgs = 0 THEN 'unanswered'
      WHEN gave_link THEN 'dropped'
      ELSE 'resolved'
    END AS outcome
  FROM scored s
);

-- Autonomy by intent, last 90 days: what the agent answers on its own, drafts
-- or escalates, and the evidence for changing that. ready_to_promote: Chris
-- sent >= 90% of at least 20 drafts unchanged (promotion is a person's call,
-- a code change with a test). demoted: the service moved it back to draft
-- after repeated rescues (learning.py) and nobody has promoted it since.
CREATE OR REPLACE VIEW `goji-bi.marts.wa_agent_intent_autonomy` AS
WITH e AS (
  SELECT * FROM `goji-bi.marts.wa_agent_events`
  WHERE `at` >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
),
p AS (
  SELECT intent, COUNT(*) AS proposals,
         COUNTIF(decision = 'send') AS auto_sent,
         COUNTIF(decision = 'draft') AS drafted,
         COUNTIF(decision = 'escalate') AS escalated
  FROM e WHERE event = 'proposal' AND intent IS NOT NULL
  GROUP BY intent
),
x AS (
  SELECT intent,
         COUNTIF(draft_outcome = 'sent_unchanged') AS drafts_sent_unchanged,
         COUNTIF(draft_outcome IN ('edited', 'replaced')) AS drafts_edited,
         COUNTIF(IFNULL(rescue, FALSE)) AS rescues
  FROM e WHERE event = 'echo' AND intent IS NOT NULL
  GROUP BY intent
),
d AS (
  SELECT intent, ARRAY_AGG(reason ORDER BY `at` DESC LIMIT 1)[SAFE_OFFSET(0)] AS last_change
  FROM `goji-bi.marts.wa_agent_events`
  WHERE event = 'autonomy' AND intent IS NOT NULL
  GROUP BY intent
)
SELECT
  p.intent, p.proposals, p.auto_sent, p.drafted, p.escalated,
  IFNULL(x.drafts_sent_unchanged, 0) AS drafts_sent_unchanged,
  IFNULL(x.drafts_edited, 0) AS drafts_edited,
  IFNULL(x.rescues, 0) AS rescues,
  SAFE_DIVIDE(p.auto_sent, p.proposals) AS auto_share,
  IFNULL(x.drafts_sent_unchanged + x.drafts_edited >= 20
         AND SAFE_DIVIDE(x.drafts_sent_unchanged, x.drafts_sent_unchanged + x.drafts_edited) >= 0.9,
         FALSE) AS ready_to_promote,
  IFNULL(STARTS_WITH(d.last_change, 'demoted'), FALSE) AS demoted
FROM p
LEFT JOIN x USING (intent)
LEFT JOIN d USING (intent);
