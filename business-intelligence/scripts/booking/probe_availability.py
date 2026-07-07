"""
Read-only probe: print derived 30-min availability for a service/date, and
cross-check against Plato's own hourly onlineapptbooking/slots.

    PLATO_API_KEY=... python3 -m booking.probe_availability 2026-07-08 physiotherapy

Safe — no writes.
"""
from __future__ import annotations

import sys
from datetime import date

from .availability import derive_availability
from .config import SERVICES
from .plato import PlatoClient


def main() -> None:
    day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    service = sys.argv[2] if len(sys.argv) > 2 else "physiotherapy"
    plato = PlatoClient()

    print(f"== {service} on {day} ({day.strftime('%a')}) — derived 30-min slots ==")
    for cid, slots in derive_availability(plato, service, day).items():
        print(f"  {cid:12} ({len(slots):2}): {', '.join(slots) or '(none)'}")

    if SERVICES[service]["supports_home"]:
        print(f"== {service} HOME VISIT (Cheryl only, +/-30m travel) ==")
        for cid, slots in derive_availability(plato, service, day, home=True).items():
            print(f"  {cid:12} ({len(slots):2}): {', '.join(slots) or '(none)'}")

    print("== Plato's own hourly onlineapptbooking/slots (for comparison) ==")
    obcal = SERVICES[service]["online_calendar"]
    data = plato.get("onlineapptbooking/slots",
                     {"calendar_id": obcal, "month": day.strftime("%Y-%m")})
    for r in data.get("rules", []):
        s = r.get("slots", {}).get(day.isoformat(), [])
        print(f"  {r.get('name'):12}: {', '.join(s) or '(none)'}")


if __name__ == "__main__":
    main()
