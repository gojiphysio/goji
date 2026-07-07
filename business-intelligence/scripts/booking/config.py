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
HOME_TRAVEL_MINUTES = 30  # travel block before AND after a home visit

# clinician_id -> Plato calendar `color` (the appointment calendar) + doctor code
CLINICIANS: dict[str, dict] = {
    "cheryl-long": {"name": "Cheryl Long", "calendar": "blue", "doctor": "PCL"},
    "claire-ng": {"name": "Claire Ng", "calendar": "6hpO", "doctor": "PCN"},
    "kristy-ng": {"name": "Kristy Ng", "calendar": "green", "doctor": "PKN"},
}

# website service id -> Plato mapping.
# online_calendar: the onlineapptbooking calendar whose rules define hours/coverage.
# type_code: Plato "Appointment Type" (code_Bottom).
# duration_min: appointment length used for slot occupancy (clinic books hourly;
#   confirm 55 vs 60 with the clinic — using 60 to match observed real bookings).
SERVICES: dict[str, dict] = {
    "physiotherapy": {
        "title": "Physiotherapy",
        "online_calendar": "dDIjWJp",  # Women's/Pelvic (all three clinicians)
        "type_code": "hDWW",
        "duration_min": 60,
        "supports_home": True,
    },
    "mummy-baby": {
        "title": "Mummy & Baby Assessment",
        "online_calendar": "z1xE8rP",  # Paediatric (Cheryl + Kristy)
        "type_code": "hDWW",
        "duration_min": 90,
        "supports_home": True,
    },
    "clinical-pilates": {
        "title": "Clinical Pilates",
        "online_calendar": "ne8sgkb",  # Cheryl + Claire
        "type_code": "2kV4",
        "duration_min": 60,
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

# Home visits: Cheryl only, typed "Home Visit" in Plato regardless of service.
HOME_VISIT_CLINICIAN = "cheryl-long"
HOME_VISIT_TYPE_CODE = "sCla"


def clinician_by_calendar(color: str) -> str | None:
    """Reverse-lookup a clinician_id from a Plato calendar `color`."""
    for cid, meta in CLINICIANS.items():
        if meta["calendar"] == color:
            return cid
    return None
