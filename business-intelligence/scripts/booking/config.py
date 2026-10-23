"""
Booking-service config — the Plato mapping for the website's booking form.

Mirrors the website's `src/lib/services.ts` + `src/lib/clinicians.ts`; keep the
two in sync (single source of truth is the clinic's Plato online-booking config,
`GET /onlineapptbooking/list`, validated 2026-07-07).

Slot granularity is 30 min, derived here rather than taken from Plato's own
`onlineapptbooking/slots` (which is locked to a 60-min `interval` that is not
changeable via the API). Home visits are Cheryl-only and padded with travel.
"""
from __future__ import annotations

SLOT_MINUTES = 30
SATURDAY_SLOT_MINUTES = 60  # Saturdays: on-the-hour slots only (no :30 slots)
HOME_TRAVEL_MINUTES = 30  # travel block before AND after a home visit
MAX_ADVANCE_DAYS = 60  # bookings are capped at 60 days into the future

# clinician_id -> Plato calendar `color` (the appointment calendar) + doctor code.
# online_start / online_end (optional) clamp the online-bookable window when the
# clinic's intended online hours differ from the raw Plato rule hours. Cheryl's
# online bookings don't start until 09:00 (her rule says 08:00).
# `email` is the clinician's work inbox; the matched clinician is CC'd on the
# internal booking heads-up so the assigned physio sees their own new bookings.
CLINICIANS: dict[str, dict] = {
    # Cheryl is fixed 09:00-17:00, Mon-Fri (Sat/Sun already off in Plato rules).
    "cheryl-long": {"name": "Cheryl Long", "calendar": "blue", "doctor": "PCL",
                    "online_start": "09:00", "online_end": "17:00",
                    "email": "cheryl.long@gojiphysio.com"},
    "claire-ng": {"name": "Claire Ng", "calendar": "6hpO", "doctor": "PCN",
                  "email": "claire.ng@gojiphysio.com"},
    "kristy-ng": {"name": "Kristy Ng", "calendar": "green", "doctor": "PKN",
                  "email": "kristy.ng@gojiphysio.com"},
    # Pilates Instructor (not a physio): Private Pilates only (SERVICE_CLINICIANS).
    "camille-tan": {"name": "Camille Tan", "calendar": "pF9S", "doctor": "ICT",
                    "email": "movement.with.camille@gmail.com"},
}

# website service id -> Plato mapping.
# online_calendar: the onlineapptbooking calendar whose rules define hours/coverage.
# type_code: Plato "Appointment Type" (code_Bottom).
# duration_min: appointment length used for slot occupancy (clinic books hourly;
#   confirm 55 vs 60 with the clinic — using 60 to match observed real bookings).
# variants: optional duration variants (e.g., paediatric physio offers 30-min and
#   55-min options with different pricing). Keyed by variant id (e.g., "30min").
SERVICES: dict[str, dict] = {
    "physiotherapy": {
        "title": "Physiotherapy",
        "online_calendar": "dDIjWJp",  # Women's/Pelvic (all three clinicians)
        "type_code": "hDWW",
        "duration_min": 60,
        "supports_home": True,
        "variants": {
            "30min": {"duration_min": 30, "price": 160, "description": "Only if prescribed by physio"},
            "45min": {"duration_min": 45, "price": 230, "description": "Review session"},
            "55min": {"duration_min": 55, "price": 260, "description": "Initial consultation"},
        },
        "variant_focus": "paediatrics",  # variants only apply to this physio sub-type
    },
    "mummy-baby": {
        "title": "Mummy & Baby Assessment",
        "online_calendar": "z1xE8rP",  # Paediatric (Cheryl + Kristy)
        "type_code": "hDWW",
        "duration_min": 85,  # matches the website (services.ts); was 90
        "supports_home": True,
    },
    "clinical-pilates": {
        "title": "Clinical Pilates",
        "online_calendar": "ne8sgkb",  # Cheryl + Claire
        "type_code": "2kV4",
        "duration_min": 60,
        "supports_home": False,
    },
    "private-pilates": {
        "title": "Private Pilates",
        "online_calendar": "vXKlwa7",  # Camille (pF9S)
        "type_code": "N1z9",  # Plato appointment type "Private Pilates"
        # Plato "Space Requirement" (code_Left): "Reformer needed".
        "space_code": "YS06",
        "duration_min": 60,  # same hourly booking as Clinical Pilates
        "supports_home": False,
    },
    "strength-conditioning": {
        "title": "Strength & Conditioning",
        "online_calendar": "XV1FDpu",  # Kristy + Claire
        "type_code": "qLbH",
        "duration_min": 60,
        "supports_home": False,
    },
}

# Physiotherapy sub-type (the website's "What type of physiotherapy?" step) ->
# label written into the Plato appointment note, so the clinic can see what a
# physio session is for (the Plato calendar/type is the same for all of them).
# Mirrors the ids in the website's src/lib/physioCategories.ts; keep in sync.
PHYSIO_FOCUS_LABELS: dict[str, str] = {
    "general": "General Musculoskeletal (MSK)",
    "womens-health": "Women's Health",
    "paediatrics": "Paediatrics",
    "scoliosis": "Scoliosis (Schroth Method)",
    "others": "Others",
}

# Physiotherapy sub-type -> the clinician_ids whose calendars open for it, so
# availability (and first-available assignment) is restricted to who actually
# offers that sub-type (e.g. scoliosis -> Cheryl only). Mirrors `clinicianIds`
# in the website's src/lib/physioCategories.ts; keep the two in sync.
PHYSIO_FOCUS_CLINICIANS: dict[str, list[str]] = {
    "general": ["cheryl-long", "claire-ng", "kristy-ng"],
    "womens-health": ["claire-ng", "kristy-ng"],
    "paediatrics": ["kristy-ng", "cheryl-long"],
    "scoliosis": ["cheryl-long"],
    "others": ["cheryl-long", "claire-ng", "kristy-ng"],
}

# "First available" auto-assignment order. When a patient lets us pick the
# clinician (the website's "Earliest available" option — the default path for a
# new patient), we walk this order and take the first clinician who is actually
# free at the chosen slot AND offers the chosen sub-type (availability still
# decides; this only breaks the tie between clinicians who are all free). Kristy
# first, then Claire, and Cheryl only as a fallback — this keeps Cheryl's diary
# open for the work only she covers (scoliosis, home visits). Any clinician not
# listed here sorts last, in config order.
FIRST_AVAILABLE_PRIORITY: list[str] = ["kristy-ng", "claire-ng", "cheryl-long"]

# Service-clinician eligibility: which clinicians are rostered to provide each
# service. If empty/absent, all clinicians in the service's online_calendar are
# eligible (the default). When populated, availability is restricted to the
# listed clinicians; this enforces service-specific roster changes (e.g. removing
# a clinician from one service while keeping them in others).
SERVICE_CLINICIANS: dict[str, list[str] | None] = {
    "clinical-pilates": ["claire-ng"],  # Cheryl Long removed from Clinical Pilates
    "private-pilates": ["camille-tan"],  # instructor-led; physios are not rostered
}

# Clinician restricted blocks: hard-coded time blocks that override Plato's
# recurring entries when they're not being detected properly. Format:
# {"clinician_id": [{"day": "Mon"|"Tue"|..., "starttime": "HH:MM", "endtime": "HH:MM"}, ...]}
# Example: block Kristy's Wednesdays 5:30-8:00pm
CLINICIAN_RESTRICTED_BLOCKS: dict[str, list[dict]] = {
    "kristy-ng": [
        {"day": "Wed", "starttime": "17:30", "endtime": "20:00"},
    ],
}

# Home visits: Cheryl only, typed "Home Visit" in Plato regardless of service.
HOME_VISIT_CLINICIAN = "cheryl-long"
HOME_VISIT_TYPE_CODE = "sCla"


def clinician_by_calendar(color: str) -> str | None:
    """Reverse-lookup a clinician_id from a Plato calendar `color`."""
    for cid, meta in CLINICIANS.items():
        if meta["calendar"] == color:
            return cid
    return None
