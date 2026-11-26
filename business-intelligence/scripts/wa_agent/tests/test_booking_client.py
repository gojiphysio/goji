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
                                          "time": "15:30", "clinician_name": "Claire Ng"})
    assert t.startswith("All booked! Thu 26 Nov, 3:30pm with Claire (ref GOJI-1).")
    assert "TEST" not in t


def test_booking_for_someone_else_names_the_patient_and_notes_who_booked(monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "BOOKING_SIMULATE", False)
    seen = {}

    class Http:
        def post(self, url, json, timeout, headers):
            seen.update(json)
            return NS(json=lambda: {"ok": True, "reference": "R", "date": json["date"],
                                    "time": json["time"]})
    b = {**B, "full_name": "Mei Tan", "for_whom": "wife", "booked_by": "Charles", "patient_age": ""}
    booking_client.book(b, wa_id="6582823628", http=Http())
    assert seen["name"] == "Mei Tan" and seen["phone"] == "+6582823628"
    assert seen["notes"].startswith("Booked via WhatsApp by Charles (wife of the patient)")
    t = booking_client.confirmation_text({"reference": "R", "date": "2026-11-23", "time": "08:00",
                                          "clinician_name": "Kristy"})
    assert t.startswith("All booked! Mon 23 Nov, 8:00am with Kristy")


def test_email_check_asks_only_about_an_email_that_wont_arrive():
    assert booking_client.email_check("") == ""                            # never required
    assert booking_client.email_check("jamie@example.com") == ""
    assert "doesn't look quite right" in booking_client.email_check("jamie at gmail")
    ask = booking_client.email_check(
        "jamie@gmail.con", "That email looks like a typo — did you mean jamie@gmail.com? "
                           "Please correct it so we can send your confirmation.")
    assert "did you mean jamie@gmail.com?" in ask


def test_confirmation_mentions_the_email_only_when_one_went_out():
    res = {"date": "2026-11-26", "time": "10:00", "clinician_name": "Kristy Ng",
           "reference": "GOJI-1"}
    assert "confirmation email" in booking_client.confirmation_text(res, emailed=True)
    assert "confirmation email" not in booking_client.confirmation_text(res)
    assert "confirmation email" not in booking_client.confirmation_text(
        {**res, "dry_run": True}, emailed=True)                            # nothing was sent


def test_offered_times_can_carry_the_clinician():
    opts = "2026-11-30 17:00 Claire, 2026-12-01 08:00 Kristy, 2026-12-02 09:00"
    assert booking_client.offered(opts) == {("2026-11-30", "17:00"), ("2026-12-01", "08:00"),
                                            ("2026-12-02", "09:00")}
    assert booking_client.offered_with(opts, "2026-11-30", "17:00") == "claire"
    # The model's clinician can't move a time to someone it wasn't offered with.
    assert booking_client.offered_with(opts, "2026-11-30", "17:00", "Kristy") == "claire"
    assert booking_client.offered_with(opts, "2026-12-02", "09:00", "Kristy Ng") == "kristy"
    assert booking_client.offered_with(opts, "2026-12-02", "09:00") == ""
    assert booking_client.offered_with(opts, "2026-12-03", "09:00") is None


def test_the_same_time_with_two_clinicians_books_the_one_they_named():
    opts = "2026-11-30 17:00 Kristy, 2026-11-30 17:00 Claire"
    assert booking_client.offered_with(opts, "2026-11-30", "17:00", "Claire") == "claire"
    assert booking_client.offered_with(opts, "2026-11-30", "17:00") == "kristy"   # newest


def test_earlier_offers_are_kept_behind_the_new_ones():
    merged = booking_client.merge_options(
        "2026-12-01 08:00 Kristy, 2026-12-01 08:30 Kristy",
        "2026-11-30 17:00 Claire, 2026-12-01 08:00 Kristy")
    assert merged == ("2026-12-01 08:00 Kristy, 2026-12-01 08:30 Kristy, "
                      "2026-11-30 17:00 Claire")
    many = ", ".join(f"2026-12-{d:02d} 09:00" for d in range(1, 20))
    assert len(booking_client.offered(booking_client.merge_options(many, ""))) == \
        booking_client.MAX_OPTIONS


def test_only_known_session_lengths_reach_the_booking(monkeypatch):
    """26 Nov 2026: the model put '40 min postpartum, Bifrost/FM billing $190'
    in variant. Only goji-booking's own codes go through; terms the team
    agreed go in `arranged`."""
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "t")
    monkeypatch.setattr(config, "BOOKING_SIMULATE", False)
    seen = []

    class Http:
        def post(self, url, json, timeout, headers):
            seen.append(json)
            return NS(json=lambda: {"ok": True, "reference": "R", "date": json["date"],
                                    "time": json["time"]})
    booking_client.book({**B, "variant": "40 min postpartum, FM billing $190",
                         "arranged": " Bill to FM, $190 for 40 min "}, wa_id="65", http=Http())
    booking_client.book({**B, "variant": "40min"}, wa_id="65", http=Http())
    assert seen[0]["variant"] == "" and seen[0]["arranged"] == "Bill to FM, $190 for 40 min"
    assert seen[1]["variant"] == "40min" and seen[1]["arranged"] == ""


def test_a_missing_name_is_asked_for_with_the_time_held():
    b = {**B, "full_name": "", "date": "2026-11-30", "time": "17:00", "clinician": "claire"}
    assert booking_client.missing_details(b) == ["full_name"]
    assert booking_client.details_question(b, ["full_name"]) == (
        "Lovely! Could I have your full name? Then I'll book Mon 30 Nov, 5:00pm with Claire "
        "for you.")
    home = {**b, "format": "home", "for_whom": "son"}
    assert booking_client.missing_details(home) == ["full_name", "address"]
    assert "the patient's full name and the address for the home visit" in \
        booking_client.details_question(home, ["full_name", "address"])
    assert booking_client.missing_details({**b, "time": ""}) == []
