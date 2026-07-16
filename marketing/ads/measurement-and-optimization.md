# Ads measurement & optimization — feeding Google high-conviction signal

**Status: parked strategy (2026-07-14), revisit after launch.** Captures how we
monitor the Search campaign and, more importantly, how we feed Google the right
conversion signal so Smart Bidding finds users who actually book *and show up* —
not just form-fillers. Grounded in the current data stack (`business-intelligence`).

## Core principle

Smart Bidding optimizes toward whatever you call a "conversion." Feed it
form-fills and it finds form-fillers (incl. no-shows). Feed it "who showed up and
paid" and it finds those people. The work is a **signal-quality ladder**: keep
upgrading what we send Google from "submitted a form" toward "became a paying,
returning patient."

## What we already have (the unlock)

| Asset | Where | Why it matters |
|---|---|---|
| gclid captured at landing | `marts.web_session_events` | Ties a Google click to everything downstream |
| gclid on the booking | `marts.booking_funnel_events` (`gclid`, `go_click_id`) | A confirmed booking is traceable to the ad click |
| Real paid value + attendance | `stg/invoices`, `marts.fct_invoice_line`, `marts.fct_patient_retention` | The high-conviction outcome: showed up, paid $X, returned |
| Ingest job pattern | `scripts/ingestion/` (`marketing_ingest`) | Reverse it to *export* conversions |
| WhatsApp intent | `marts.link_click_events` (`gbp-wa`, `web-wa`) | Leading intent signal (marketing/AGENTS.md) |

## The conviction ladder — what to feed Google

| Level | Signal | Conviction | Feasible now? |
|---|---|---|---|
| L0 (today) | `booking_confirmed` form event | low–mid | ✅ wired |
| L1 | Value-based: pass service price as conversion value | mid | ✅ nearly free |
| L2 | WhatsApp-click + booking-start as secondary/observation | signal density | ✅ events exist |
| L3 | Offline Conversion Import of confirmed booking via `gclid` | mid–high | ✅ gclid in funnel |
| L4 | OCI of *attended + paid* value (incl. packages) | highest | ⚠️ needs gclid↔appointment bridge |
| L5 | Customer Match / Enhanced Conversions (patient emails/phones) | high | 🚫 health-data compliance landmine |

## The three moves, in order

**1. Value-based bidding (launch — cheapest big win).** Real price
differentiation exists ($260 clinic / $330 home / packages). Pass the actual
service value into the conversion, not a flat count → bidding shifts from "most
bookings" to "most revenue"; `tCPA` becomes `tROAS`. The booking form already
knows the service.

**2. Solve cold-start (launch).** At ~SGD 20/day, confirmed bookings are sparse
and Smart Bidding (needs ~15–30/mo) will starve. Set `booking_confirmed` as the
**Primary** bidding conversion; add WhatsApp-click + booking-start as
**Secondary (observation only)** for funnel visibility without polluting the bid.
Stay on Maximize Clicks until volume supports Maximize Conversions.

**3. OCI on attended + paid — the compounding lever (Phase 5).**
Honest constraint: the web funnel is deliberately PII-free
(`booking_funnel_events`: "not linkable to a patient") and invoices join on
`patient_id`, so there's no existing gclid→paid-appointment bridge — and that
boundary is worth keeping. Path through: the `goji-booking` service holds *both*
the beacon gclid and the Plato appointment at booking time. At the `confirmed`
stage, write a **restricted** `gclid ↔ plato_appointment_id ↔ booked_value`
mapping to a locked-down table (not public marts). A new
`google_ads_oci_export` Cloud Run Job (mirror of the `google_ads` ingest) joins
that mapping to attendance/invoice outcome and uploads OCI (gclid, time, SGD
value) via the Google Ads API. Public marts stay PII-free; the bridge is
least-privilege.

## The WhatsApp gap (our #1 intent signal)

WhatsApp is off-site, so Google can't see it natively. (a) Feed click-to-WhatsApp
as a low-value secondary conversion so Google sees the intent; (b) Ads-sourced
visitors (have a gclid) who later convert via WhatsApp still flow through the OCI
path. Unfeedable case: WhatsApp-first visitors who never hit the site with a
gclid — accept it; judge Ads on the on-site path.

## Compliance landmine — L5

Customer Match / Enhanced Conversions upload patient contact data. For a
women's-health / pelvic-floor clinic that is **sensitive-category health data** —
Google policy restricts using sensitive health info for personalization, and
PDPA + `strategy/03` both apply. **Do not do L5 without a lawyer / PDPA review.**
The highest-conviction lever (L4) runs on gclid — a click id, not patient
identity — so we get the biggest win while staying PII-clean on Google's side.

## Monitoring layer

- **Marketing-tab cards:** GSC (`marts.gsc_search_performance`, P1 ingest job),
  Ads spend (existing `google_ads` transfer → `fetch_google_ads`), and a new
  booking-funnel card from `booking_funnel_events`.
- **North-star metric evolves:** cost-per-form-fill → cost-per-confirmed →
  cost-per-attended-booking → ROAS as L1/L4 land.
- **Funnel drop-off** from logged stages (`page_view → service_selected →
  time_selected → details → submitted → confirmed`) — shows *where* high-intent
  users leak, so we fix the page, not just the bid.
- **Weekly search-terms ritual** (campaign plan §9–10) — human-in-the-loop signal
  improvement.

## Recommended sequence

L1 + L2 at launch (cheap, no PII) → L3 once bookings flow → L4 as the Phase-5
compounding project → skip L5 pending compliance.
