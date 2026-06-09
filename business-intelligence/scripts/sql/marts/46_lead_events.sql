-- marts.lead_events  (+ marts.lead_latest)
--
-- Inbound-lead pipeline for the front-desk portal's "Leads" tab. Tracks every
-- WhatsApp / Instagram / etc. inquiry from first contact through to won/lost,
-- so we can measure how many inquiries come in, how many we close, and where we
-- leak. Append-only event log: capturing a lead and every stage change writes
-- one new row. We never UPDATE or DELETE — the current state of a lead is the
-- latest event by updated_at. Same idiom as patient_followup_events /
-- appt_confirmation_events, and it sidesteps BigQuery's restrictions on mutating
-- recently-streamed rows.
--
-- This is the structured replacement for the founder Marketing tab's manual
-- enquiry log: it adds a contact key and explicit funnel stages, and it's the
-- middle of the acquisition funnel — the click is already logged
-- (marts.link_click_events, slug = channel) and the first visit lands in Plato;
-- the lead is the named person in between.
--
-- PII NOTE — deliberate exception. Unlike the patient worklists (which key on
-- patient_id and hydrate name/phone live from marts.dim_patient_contact), a lead
-- is a *pre-patient*: they aren't in Plato yet, so there's nothing to hydrate
-- from. `contact` (phone or @handle) is therefore stored here — it's the only
-- record of who the lead is, and the dedup key. Access stays gated to
-- founder+staff on the frontdesk subdomain with a table-level dataEditor grant;
-- keep `note` operational, not clinical.
--
-- channel values (reuse the enquiry-log / LINK_SLUGS vocabulary):
--   whatsapp | instagram | google | referral | walk_in | form | call | other
-- stage values (append-only transitions):
--   inquiry   — just came in (the default on capture).
--   qualified — a real prospect (engaged, fits who we treat). Optional middle.
--   booked    — first appointment scheduled.
--   won       — attended their first visit / now a paying patient or customer.
--               NB: "won" = became a patient, NOT "bought a package" — packages
--               are a separate worklist and not a funnel stage.
--   lost      — didn't convert. lost_reason captures why (free text).
--
-- Each write carries the lead's full current snapshot (contact + channel + note),
-- so the latest row is self-sufficient for display — no coalescing needed.
--
-- Created as a real table (not a view). CREATE TABLE IF NOT EXISTS is
-- idempotent, so deploy_all.sh can run it repeatedly without clobbering data.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.lead_events` (
  event_id    STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  lead_id     STRING    NOT NULL OPTIONS(description="Stable id for the lead (UUID minted on first capture)"),
  name        STRING    OPTIONS(description="Lead's name (optional — an inbound message often arrives before we know it). Pre-patient PII, stored deliberately."),
  contact     STRING    OPTIONS(description="Phone or @handle — who the lead is, and the dedup key. Pre-patient PII, stored deliberately."),
  channel     STRING    OPTIONS(description="whatsapp | instagram | google | referral | walk_in | form | call | other"),
  stage       STRING    NOT NULL OPTIONS(description="inquiry | qualified | booked | won | lost"),
  lost_reason STRING    OPTIONS(description="For stage=lost: why the lead didn't convert (free text)"),
  note        STRING    OPTIONS(description="Free-text operational note from the front desk"),
  updated_by  STRING    OPTIONS(description="Auth username of the staff member who took the action"),
  updated_at  TIMESTAMP NOT NULL OPTIONS(description="When the event was recorded")
);

-- `name` was added after the table first shipped. CREATE TABLE IF NOT EXISTS
-- won't alter an existing table, so add the column explicitly — idempotent, and
-- a no-op once the column exists (and for fresh installs the CREATE already has it).
ALTER TABLE `goji-bi.marts.lead_events`
  ADD COLUMN IF NOT EXISTS name STRING
  OPTIONS(description="Lead's name (optional). Pre-patient PII, stored deliberately.");

-- Latest event per lead, plus first_seen (when the lead first came in) so the
-- funnel can bucket inquiries by period. The Leads tab reads this for the
-- worklist and the founder Marketing funnel cards aggregate it.
CREATE OR REPLACE VIEW `goji-bi.marts.lead_latest` AS
SELECT
  lead_id, name, contact, channel, stage, lost_reason, note, updated_by, updated_at, first_seen
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY lead_id ORDER BY updated_at DESC) AS _rn,
    MIN(updated_at) OVER (PARTITION BY lead_id)                       AS first_seen
  FROM `goji-bi.marts.lead_events`
)
WHERE _rn = 1;
