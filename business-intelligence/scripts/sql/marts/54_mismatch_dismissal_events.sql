-- marts.mismatch_dismissal_events  (+ marts.mismatch_dismissal_latest)
--
-- Persistent dismissals for the founder dashboard's "Provider attribution
-- alerts" (invoice doctor disagrees with the same-day appointment-calendar
-- doctor — see 30_fct_invoice_doctor_mismatches.sql). Dismissing an alert used
-- to be browser-local only (localStorage, 7-day TTL), so it evaporated and
-- didn't carry across devices. This is the server-side store: append-only event
-- log, exactly like marketing_ops_events / patient_followup_events. Every
-- dismiss / restore writes one new row; we never UPDATE or DELETE. The current
-- state of an invoice's alert is the latest event by updated_at.
--
--   action  — 'dismissed' (hide the live alert for this invoice) or 'restored'
--             (un-dismiss: the alert reappears if the invoice still mismatches).
--   reason  — optional free-text note from the founder ("Kristy covered for
--             Claire that day"). Operational, not clinical; no patient PII
--             beyond the initial+lastname the alert already shows.
--
-- Dismissal is keyed on invoice_id only: once dismissed, that invoice stays
-- silenced regardless of later edits (a deliberate product choice — Restore from
-- the Alert-history tab is the escape hatch). The live alert already self-heals
-- the other way: when an invoice is corrected in Plato it drops off
-- fct_invoice_doctor_mismatches, so most dismissals are belt-and-braces.
--
-- The remaining columns snapshot what the alert showed at dismiss time
-- (invoice label/date, patient, the doctor flip, total, who created/edited the
-- invoice) so the Alert-history tab can render the row even after the invoice
-- has fallen out of the 30-day mismatch window or been corrected. The client
-- owns the snapshot (it has the row in hand), same as lead_events.
--
-- Created as a real table (not a view). CREATE TABLE IF NOT EXISTS is
-- idempotent, so deploy_all.sh can run it repeatedly without clobbering data.

CREATE TABLE IF NOT EXISTS `goji-bi.marts.mismatch_dismissal_events` (
  event_id       STRING    NOT NULL OPTIONS(description="UUID for this event row"),
  invoice_id     STRING    NOT NULL OPTIONS(description="Plato invoice id the dismissal applies to"),
  action         STRING    NOT NULL OPTIONS(description="dismissed | restored"),
  reason         STRING    OPTIONS(description="Optional free-text note. Operational, never clinical."),
  invoice_label  STRING    OPTIONS(description="Snapshot: invoice number/label shown in the alert"),
  invoice_date   DATE      OPTIONS(description="Snapshot: invoice date"),
  patient        STRING    OPTIONS(description="Snapshot: patient initial+lastname as shown in the alert"),
  invoice_doctor STRING    OPTIONS(description="Snapshot: the invoice doctor (the 'wrong' side of the flip)"),
  appt_doctors   STRING    OPTIONS(description="Snapshot: same-day appointment doctor(s), joined ' / '"),
  total          NUMERIC   OPTIONS(description="Snapshot: invoice total"),
  created_by     STRING    OPTIONS(description="Snapshot: who created the invoice in Plato"),
  last_edited_by STRING    OPTIONS(description="Snapshot: who last edited the invoice in Plato"),
  updated_by     STRING    OPTIONS(description="Auth username of the founder/staff who dismissed or restored"),
  updated_at     TIMESTAMP NOT NULL OPTIONS(description="When the action was taken")
);

-- Latest action per invoice, carrying the snapshot from that row. The dashboard
-- reads this two ways: (1) filter the live alert list to drop invoices whose
-- latest action is 'dismissed'; (2) paint the Alert-history tab from the same
-- dismissed rows (with a Restore button that appends action='restored').
CREATE OR REPLACE VIEW `goji-bi.marts.mismatch_dismissal_latest` AS
SELECT
  invoice_id, action, reason, invoice_label, invoice_date, patient,
  invoice_doctor, appt_doctors, total, created_by, last_edited_by,
  updated_by, updated_at
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY invoice_id ORDER BY updated_at DESC) AS _rn
  FROM `goji-bi.marts.mismatch_dismissal_events`
)
WHERE _rn = 1;
