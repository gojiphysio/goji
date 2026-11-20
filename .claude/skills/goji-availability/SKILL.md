---
name: goji-availability
description: Look up live free times and bookable slots for Goji Health clinicians (Cheryl Long, Claire Ng, Kristy Ng, Camille Tan) from the clinic's Plato diary through the public booking API. Use this whenever someone asks when a Goji physio or Pilates instructor is free, open, available or booked up ("what's Cheryl's free time next week", "can Kristy fit someone in Thursday", "earliest clinical pilates slot", "is anyone free for a home visit Tuesday"), or wants slots to offer a patient on WhatsApp, even if they don't say "Plato" or "availability". Read-only, so it can't create, move or cancel appointments.
---

# Goji clinician availability

Goji's appointments live in Plato. The website's booking backend
(`https://booking.gojiphysio.com`) reads Plato server-side and applies the
clinic's real rules: working hours, leave blocks, the shared reformer,
which clinician does which service, and the 60-day booking window. This skill
reads that backend, so the answers match what a patient sees on the website,
and no Plato key is needed.

## How to run it

Run the bundled script. It uses only the Python standard library:

```bash
python scripts/availability.py --clinician cheryl-long --next-week
python scripts/availability.py --clinician all --from 2026-12-01 --days 5
python scripts/availability.py --service clinical-pilates --next-week
python scripts/availability.py --service physiotherapy --focus scoliosis --from 2026-12-01 --days 14
python scripts/availability.py --clinician cheryl-long --service physiotherapy --home --next-week
```

Options:
- `--clinician`: `cheryl-long`, `claire-ng`, `kristy-ng`, `camille-tan` or `all` (the default)
- Dates: `--next-week` (next Monday to Sunday), or `--from YYYY-MM-DD` with `--to` or `--days`. The default is 7 days from today. Dates are in Singapore time.
- `--service`: `physiotherapy`, `mummy-baby`, `clinical-pilates`, `private-pilates` or `strength-conditioning`
- `--variant`: `30min`, `45min` or `55min` (physio only). `--focus`: `general`, `womens-health`, `paediatrics`, `scoliosis` or `others`
- `--home`: a home visit (Cheryl only), which adds 30 min of travel either side
- `--json`: structured output

Work out relative dates such as "next week" or "Thursday" from today's date in
Singapore, and put the actual dates in your answer.

## Two kinds of question

**"When is X free?"** Leave out `--service`. The script reads each physio's
diary at 30-minute granularity and merges the free blocks into windows such as
`15:00-17:00`. This is the right view for internal planning, because it shows
gaps a 60-minute booking would hide. Camille only does Private Pilates, so her
diary is read in 60-minute blocks.

**"What can a patient book?"** Pass `--service`, plus `--focus`, `--variant` or
`--home` where they apply. The output is the start times the website would
offer for that service. Use this view when drafting slots to send a patient.

## Answering

- Give a short table or list by day. Say which view it is (free windows, or
  bookable start times for a service) and the time you read it.
- Call out days with no availability. Cheryl works Monday to Friday, 09:00 to
  17:00, for online bookings.
- The data is live but can change at any moment, and the backend's snapshot
  refreshes about every 5 minutes. Treat a slot as a guide, not a hold. To
  secure one, the patient books on the website (route them through the
  `go.gojiphysio.com/<slug>` links, never a raw link) or front desk books in Plato.
- These rules follow from how the clinic is set up (source: `config.py` in the
  goji-booking service). Clinical Pilates is Claire only, and she shares the one
  reformer with Camille. Scoliosis is Cheryl only. Women's health is Claire and
  Kristy. Saturdays have hourly slots and no Pilates or S&C.

## Limits and errors

- **Read-only.** The skill can't book, cancel or see patient details. Those
  need Plato itself or the dashboard.
- **Be gentle with Plato.** Plato's API budget, about 20 requests a minute, is
  shared with the live website, so the script asks for one month summary and
  then one request per open day, with a pause between requests. Don't loop the
  script over long ranges or every clinician unless you need to. Keep to the
  60-day window.
- **The script never sends a `session_id`.** That keeps these lookups out of
  the website's booking-funnel analytics. Keep it that way if you edit the script.
- **"Could not reach booking.gojiphysio.com"** means the sandbox's network
  blocks it. In claude.ai or Cowork, an admin allows the domain for code
  execution in the organisation's settings. In a Claude Code cloud session, add
  the host to the environment's allowed domains. Say so, and don't guess
  availability.
- A `503` means Plato is busy. The script retries on its own; if it still
  fails, wait a minute and run it again.
