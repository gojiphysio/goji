---
name: book-from-whatsapp
description: Book a patient into Plato from a WhatsApp conversation, when Chris says she promised someone on WhatsApp she'd book them ("book for Sarah", "I told X I'd book her in"). Reads the chat transcript, works out the service, slot and patient details, checks availability, confirms with Chris, dry-runs, then books through goji-booking.
---

# Book from a WhatsApp conversation

Chris (the owner) runs WhatsApp from the Business app; the transcript also
lands in Firestore via the wa_agent. Use it to book what was agreed in the
chat. First used 25 Nov 2026.

Scripts live next to this file in `scripts/`. Put any working files
(`booking.json`) in the scratchpad, never the repo.

## 1. Find the chat

```bash
uv run .claude/skills/book-from-whatsapp/scripts/read_chat.py "<name or number>"
```

Matches the chat's saved name, number or any message text (try the first
name, then the number). Add `--all` if the last 40 lines don't reach the
start of the request. Several matches: pick by context, or ask Chris.
Nothing found: transcripts expire after 30 days. Ask Chris for the details.
`wa_id` is the number without `+` (e.g. `6591234567` → `+6591234567`).

## 2. Work out what was agreed

Read the **whole** request, not just the last lines:

- **Service** → a `booking/config.py` `SERVICES` id (`physiotherapy`,
  `mummy-baby`, `clinical-pilates`, `private-pilates`,
  `strength-conditioning`, ...). Physiotherapy also needs `physio_focus`
  (`general`, `womens-health`, `paediatrics`, `scoliosis`, `others`);
  postpartum / pelvic floor is `physiotherapy` + `womens-health`.
  `variant` only applies to paediatric physio (else `""`).
- **Date and time** the customer said yes to last (they often settle it
  after staff offer options, e.g. "Dec 1, 10am"). Check the weekday matches.
- **Full name and email** as the customer typed them (the chat name may
  be a nickname or English name, not the name on record). Phone = the chat's own number.
- **Format** `clinic` unless a home visit was agreed (then `address`).
- **Special asks** (language, clinician, what they want assessed): go in
  `notes`, and can decide the clinician.

## 3. Check the slot and the patient

```bash
curl -s "https://booking.gojiphysio.com/api/availability?service=<id>&date=YYYY-MM-DD&physio_focus=<focus>"
```

`by_clinician` shows who is free at that time. Only clinicians in
`PHYSIO_FOCUS_CLINICIANS` / `SERVICE_CLINICIANS` for that service count.

Existing patient? Look up by number (and email):

```bash
bq query --use_legacy_sql=false --format=prettyjson "SELECT patient_id, full_name, phone, email FROM \`goji-bi.marts.dim_patient_contact\` WHERE REGEXP_CONTAINS(phone, r'<last 8 digits>') OR LOWER(email) = '<email>'"
```

A match → `patient_id`, `create_patient: false`. None → `patient_id: ""`,
`create_patient: true`. (If the person booking is someone else on that
number, e.g. a parent booking for a child, it's a new patient: ask Chris.)

## 4. Confirm with Chris before booking

One AskUserQuestion stating: full name and number, service, date + weekday,
time, clinician, format. Raise anything you couldn't settle from the chat
(the slot is gone, two clinicians free and the customer had a preference,
a language or clinician ask you can't verify: the repo doesn't record who
speaks what). Don't book on a guess.

## 5. Dry run, then book

Write `booking.json` to the scratchpad (fields in `scripts/book.py`'s
docstring; `notes` starts "Booked via WhatsApp by Chris." then the
customer's asks), then:

```bash
python3 -I .claude/skills/book-from-whatsapp/scripts/book.py <scratchpad>/booking.json
```

```bash
python3 -I .claude/skills/book-from-whatsapp/scripts/book.py <scratchpad>/booking.json --real
```

Run the real one only after the dry run returns `"ok": true` and Chris has
said yes. `slot_taken` (409): re-check availability and go back to Chris.
Never call Plato directly (20 requests/min for the whole clinic).

## 6. Tell Chris

Reference, who, what, when, with whom, and what you put in the notes.
goji-booking emails the patient a confirmation when an email was given.
**The customer gets no WhatsApp message**: the chat is paused because
Chris wrote in it, and the wa_agent sends nothing into a chat Chris has.
Suggest a one-line "you're all booked" she can send herself.
