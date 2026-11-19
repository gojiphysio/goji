from types import SimpleNamespace as NS

from wa_agent import booking_client, config

B = {"service": "physiotherapy", "date": "2026-11-26", "time": "10:00", "clinician": "Kristy",
     "physio_focus": "", "variant": "", "format": "clinic", "full_name": "Charles Tan",
     "email": "", "address": "", "notes": ""}


def test_complete_needs_service_date_time_name_and_home_address():
    assert booking_client.complete(B)
    assert not booking_client.complete({**B, "full_name": " "})
    assert not booking_client.complete({**B, "time": "10am"})
    assert not booking_client.complete({**B, "format": "home"})
    assert booking_client.complete({**B, "format": "home", "address": "1 Lentor Rd"})


def test_book_posts_to_the_private_route_as_a_dry_run_by_default(monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "BOOKING_SIMULATE", False)
    seen = {}

    class Http:
        def post(self, url, json, timeout, headers):
            seen.update(url=url, body=json, headers=headers)
            return NS(json=lambda: {"ok": True, "reference": "DRYRUN-1", "dry_run": True,
                                    "date": json["date"], "time": json["time"]})
    booking_client.book(B, wa_id="6591234567", http=Http())
    assert seen["url"].endswith("/internal/book") and seen["headers"]["X-Internal-Token"] == "t"
    body = seen["body"]
    assert body["dry_run"] is True and body["phone"] == "+6591234567"
    assert body["email"] == "" and body["clinician_id"] == "kristy-ng" and body["source"] == "whatsapp"


def test_refused_booking_raises_with_its_code(monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "BOOKING_SIMULATE", False)

    class Http:
        def post(self, *a, **k):
            return NS(json=lambda: {"ok": False, "error": "gone", "code": "slot_taken"})
    try:
        booking_client.book(B, wa_id="6591234567", http=Http())
    except booking_client.BookingFailed as e:
        assert e.code == "slot_taken"
    else:
        raise AssertionError("expected BookingFailed")


def test_confirmation_text_is_built_from_the_booking_systems_answer():
    t = booking_client.confirmation_text({"reference": "GOJI-1", "date": "2026-11-26",
                                          "time": "15:30", "clinician_name": "Claire Ng"},
                                         first_name="Sam")
    assert t.startswith("You're booked, Sam! Thu 26 Nov, 3:30pm with Claire (ref GOJI-1).")
    assert "TEST" not in t
