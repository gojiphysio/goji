# Plato API - Appointments

Source: https://clinic.platomedical.com/developers/1.0/appointments
Captured: 2026-05-23

---

This guide explains how appointment calendars work, how to create appointments in a specific calendar, and how to retrieve available timeslots.

## How appointments map to calendars

Each appointment belongs to a calendar. In the API payload, this calendar is set using the `color` field.

For example, when creating an appointment with `POST /{db}/appointment`, set `color` to the calendar ID you want to book into.

```json
{
  "patient_id": "10CACFF1-9685-274C-A357-C4B20EBD369E",
  "title": "John Doe",
  "description": "Initial consult",
  "starttime": "2026-03-20 09:00:00",
  "endtime": "2026-03-20 09:15:00",
  "color": "LSG9"
}
```

`color` = calendar ID.

## Get list of available calendars

To discover valid calendar IDs, call `GET /{db}/systemsetup`. This endpoint returns system setup configuration, including the calendar definitions used by appointments.

```bash
curl -X GET "https://clinic.platomedical.com/api/DATABASENAME/systemsetup" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx"
```

Use the returned calendar ID values as the `color` field when creating or filtering appointments.

## Get available timeslots

Use `POST /{db}/appointment/slots` to retrieve available appointment slots based on your scheduling conditions.

```bash
curl -X POST "https://clinic.platomedical.com/api/DATABASENAME/appointment/slots" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "month": "Sep 2026",
    "check_for_conflicts": ["LSG9"],
    "starttime": "09:00",
    "endtime": "17:00",
    "interval": 15,
    "simultaneous": 1,
    "min_days": 1,
    "max_days": 90,
    "type": "fixed"
  }'
```

Key request fields:

- `month`: future month to search (e.g. `Sep 2026`)
- `check_for_conflicts`: calendar IDs to check for availability/conflicts
- `starttime`, `endtime`, `interval`: defines the slot window and granularity
- `simultaneous`: number of parallel appointments allowed in a timeslot
- `min_days`, `max_days`: booking-window constraints
- `type`: e.g. `fixed`

## Online appointment booking calendar slots

If using online appointment booking calendars:

- `GET /{db}/onlineapptbooking/slots?calendar_id=...&month=YYYY-MM`
- `GET /{db}/onlineapptbooking/list` to enumerate online booking calendars first

---

## Notes for Goji BI

- The `color` field doubles as calendar ID. In our schema, this becomes our **clinician/room dimension**. Pull `/systemsetup` once per day to refresh `dim_clinician` / `dim_calendar`.
- For utilization metrics we need: appointments (booked time) + calendar definitions (available windows). The `appointment/slots` endpoint shows the booking-window definition (starttime/endtime/interval) which we can reverse-engineer into `fct_clinician_capacity`.
- The `simultaneous` field is interesting: a room that supports parallel sessions has `simultaneous > 1`. Don't double-count capacity.
