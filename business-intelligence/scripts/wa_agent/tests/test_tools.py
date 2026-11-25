from types import SimpleNamespace as NS

from booking import config as booking_config
from wa_agent.events import chat_key
from wa_agent import tools


def test_service_and_focus_lists_mirror_the_booking_service():
    assert set(tools.SERVICES) == set(booking_config.SERVICES)
    assert set(tools.FOCUSES) == set(booking_config.PHYSIO_FOCUS_LABELS)


def test_tool_defs_match_handlers():
    assert {t["name"] for t in tools.TOOL_DEFS} == set(tools.HANDLERS)


def test_booking_link_goes_through_the_tracked_redirector():
    out, err = tools.run_tool("booking_link", {"service": "physiotherapy",
                                               "focus": "womens-health"}, wa_id="x")
    assert not err
    # ref is the chat's salted hash, so a booking can be credited to the chat
    assert out["url"] == ("https://go.gojiphysio.com/wa-book?"
                          f"service=physiotherapy&focus=womens-health&ref={chat_key('x')}")


def test_bad_service_is_an_error_result_not_an_exception():
    out, err = tools.run_tool("booking_link", {"service": "massage"}, wa_id="x")
    assert err and "unknown service" in out


class _Http:
    def __init__(self, status=200, payload=None):
        self.status, self.payload, self.calls = status, payload or {}, []

    def get(self, url, params, timeout, headers=None):
        self.calls.append((url, params))
        self.headers = headers
        def boom():
            raise RuntimeError(self.status)
        return NS(status_code=self.status, json=lambda: self.payload,
                  raise_for_status=(lambda: None) if self.status < 400 else boom)


def test_get_times_reads_booking_api_and_names_clinicians():
    http = _Http(payload={"times": ["09:00", "10:00"],
                          "by_clinician": {"kristy-ng": ["09:00"], "claire-ng": ["10:00"]},
                          "clinicians": [{"id": "kristy-ng", "name": "Kristy Ng"},
                                         {"id": "claire-ng", "name": "Claire Ng"}]})
    out, err = tools.run_tool("get_times", {"service": "physiotherapy", "date": "2026-11-20",
                                            "home": True}, wa_id="x", http=http)
    assert not err
    assert out["by_clinician"] == {"Kristy Ng": ["09:00"], "Claire Ng": ["10:00"]}
    url, params = http.calls[0]
    assert url.endswith("/api/availability") and params["home"] == "1"
    assert "focus" not in params  # empty values aren't sent


def test_availability_loading_is_a_retryable_error():
    out, err = tools.run_tool("find_available_dates", {"service": "physiotherapy",
                                                       "month": "2026-11"},
                              wa_id="x", http=_Http(status=503))
    assert err and "loading" in out


def test_tool_crash_is_contained():
    out, err = tools.run_tool("get_times", {"service": "physiotherapy", "date": "2026-11-20"},
                              wa_id="x", http=_Http(status=500))
    assert err and "unavailable" in out


def test_read_page_only_serves_indexed_pages():
    out, err = tools.run_tool("read_page", {"page_id": "conditions/diastasis-recti"}, wa_id="x")
    assert not err and "diastasis" in out["text"].lower()
    out, err = tools.run_tool("read_page", {"page_id": "../../secrets"}, wa_id="x")
    assert err


def test_patient_lookup_off_by_default():
    out, err = tools.run_tool("my_appointments", {}, wa_id="6591234567")
    assert not err and out["enabled"] is False


class _Avail:
    """goji-booking API stand-in: month summaries + per-day times."""

    def __init__(self, months, days):
        self.months, self.days, self.calls = months, days, []

    def get(self, url, params, timeout, headers=None):
        self.calls.append((url.rsplit("/", 1)[-1], dict(params)))
        if url.endswith("availability-summary"):
            payload = {"available": self.months.get(params["month"], [])}
        else:
            payload = self.days[params["date"]]
        return NS(status_code=200, json=lambda: payload, raise_for_status=lambda: None)


def _day(times_by):
    return {"by_clinician": times_by,
            "clinicians": [{"id": c, "name": c.split("-")[0].title()} for c in times_by]}


def test_next_slots_spreads_across_days_in_one_tool_call():
    from datetime import date
    http = _Avail(
        months={"2026-11": ["2026-11-17", "2026-11-28", "2026-11-30"], "2026-12": ["2026-12-01"]},
        days={"2026-11-28": _day({"kristy-ng": ["09:00", "10:00", "11:00", "12:00"],
                                   "claire-ng": ["10:00"]}),
              "2026-11-30": _day({"claire-ng": ["14:00"]}),
              "2026-12-01": _day({"kristy-ng": ["08:00"]})})
    out, err = tools.run_tool("next_slots", {"service": "physiotherapy", "focus": "womens-health"},
                              wa_id="x", http=http, today=date(2026, 11, 18))
    assert not err
    assert [(s["date"], s["time"]) for s in out["slots"]] == [
        ("2026-11-28", "09:00"), ("2026-11-28", "10:00"), ("2026-11-28", "11:00"),
        ("2026-11-30", "14:00"), ("2026-12-01", "08:00")]
    assert out["slots"][1]["clinicians"] == ["Kristy", "Claire"]
    assert out["slots"][0]["weekday"] == "Sat"
    # past dates skipped; two month summaries + three day lookups at most
    assert [c[0] for c in http.calls].count("availability") == 3
    assert all(c[1].get("focus") == "womens-health" for c in http.calls)


def test_patient_context_off_by_default_and_stand_in_only_locally(monkeypatch):
    from wa_agent import config as cfg
    monkeypatch.setattr(cfg, "PATIENT_LOOKUP", False)
    monkeypatch.setattr(cfg, "TEST_PATIENTS", {"6590000001": {"returning": True,
                                                             "first_name": "Sarah"}})
    monkeypatch.setattr(cfg, "STATE_BACKEND", "memory")
    assert tools.patient_context("6590000001")["first_name"] == "Sarah"
    assert tools.patient_context("6590000002") == {}
    monkeypatch.setattr(cfg, "STATE_BACKEND", "firestore")   # never on a deployed service
    assert tools.patient_context("6590000001") == {}


def test_describe_patient_keeps_it_to_name_and_dates():
    assert tools.describe_patient({}) == ""
    assert "new enquiry" in tools.describe_patient({"returning": False})
    one = tools.describe_patient({"returning": True, "first_name": "Sarah",
                                  "patients_on_number": 1, "next_appointment": None,
                                  "last_visit": "2026-10-02"})
    assert one == ("a patient record is linked to this number; record first name Sarah (the "
                   "texter may be this patient or someone booking for them); no upcoming "
                   "appointment; last visit 2026-10-02")
    shared = tools.describe_patient({"returning": True, "first_name": "Ghazal",
                                     "patients_on_number": 2,
                                     "next_appointment": {"date": "2026-11-21", "time": "16:30",
                                                          "with": "Cheryl"}})
    assert "2 patients share this number" in shared and "with Cheryl" in shared


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def query(self, sql, job_config=None):
        return NS(result=lambda: self.rows)


def test_find_booking_needs_name_and_number_to_match(monkeypatch):
    from datetime import date as _date
    from wa_agent import config as cfg
    monkeypatch.setattr(cfg, "PATIENT_LOOKUP", True)
    monkeypatch.setattr(tools, "_find_tries", {})
    row = {"appt_date": _date(2026, 11, 26), "time_sgt": "10:00", "clinician_id": "PKN",
           "name": "tan sarah mei ling"}
    bq = _Rows([row])
    ok, err = tools.run_tool("find_booking", {"full_name": "Sarah Tan", "phone": "9123 4567"},
                             wa_id="6580000000", bq=bq)
    assert not err and ok["next_appointment"] == {"date": "2026-11-26", "time": "10:00",
                                                  "with": "Kristy"}
    wrong, _ = tools.run_tool("find_booking", {"full_name": "Sarah Lim", "phone": "91234567"},
                              wa_id="6580000000", bq=bq)
    assert wrong == {"matched": False}
    one_word, _ = tools.run_tool("find_booking", {"full_name": "Sarah", "phone": "91234567"},
                                 wa_id="6580000000", bq=bq)
    assert one_word == {"matched": False}                # a first name alone isn't enough
    _, err = tools.run_tool("find_booking", {"full_name": "Sarah Tan", "phone": "91234567"},
                            wa_id="6580000000", bq=bq)
    assert err                                            # more than 3 tries in one chat


def test_record_for_booking_never_uses_the_texters_record_for_someone_else():
    p = {"records": [{"id": "CHARLES", "name": "Charles Tan"}]}
    assert tools.record_for_booking(p, "Mei Tan", "wife") == ""            # new record for her
    assert tools.record_for_booking(p, "Charles Tan", "self") == "CHARLES"
    assert tools.record_for_booking(p, "Charles", "self") == "CHARLES"      # one record, first name fits
    family = {"records": [{"id": "MUM", "name": "Lim Mei Ling"}, {"id": "KID", "name": "Lim Ethan"}]}
    assert tools.record_for_booking(family, "Ethan Lim", "son") == "KID"
    assert tools.record_for_booking(family, "Ethan", "son") == ""          # one word isn't enough
    assert tools.record_for_booking({}, "Jamie Lee", "self") == ""


def test_slot_tools_ask_for_same_day_slots_with_the_internal_token(monkeypatch):
    # Today's slots are hidden from the website (Plato's min_days); the
    # assistant sees them with the internal token (24 Nov 2026).
    http = _Http(payload={"times": [], "by_clinician": {}, "clinicians": []})
    monkeypatch.setattr(tools.config, "INTERNAL_TOKEN", "tok")
    tools.run_tool("get_times", {"service": "physiotherapy", "date": "2026-11-24"},
                   wa_id="x", http=http)
    assert http.calls[-1][1]["same_day"] == "1" and http.headers == {"X-Internal-Token": "tok"}
    monkeypatch.setattr(tools.config, "INTERNAL_TOKEN", "")
    tools.run_tool("get_times", {"service": "physiotherapy", "date": "2026-11-24"},
                   wa_id="x", http=http)
    assert "same_day" not in http.calls[-1][1] and http.headers is None


def test_next_slots_labels_todays_times_today():
    from datetime import date
    http = _Avail(months={"2026-11": ["2026-11-24", "2026-11-25"]},
                  days={"2026-11-24": _day({"claire-ng": ["15:00"]}),
                        "2026-11-25": _day({"kristy-ng": ["09:00"]})})
    out = tools.next_slots({"service": "physiotherapy"}, http=http, today=date(2026, 11, 24))
    assert [s["weekday"] for s in out["slots"]] == ["Today", "Wed"]


def test_an_email_on_file_goes_to_the_booking_never_to_the_model():
    p = {"returning": True, "first_name": "Sarah", "patients_on_number": 1,
         "records": [{"id": "S1", "name": "Sarah Lim", "email": "sarah@example.com"}]}
    assert tools.record_email(p, "S1") == "sarah@example.com"
    assert tools.record_email(p, "") == ""                                  # a new record: none
    line = tools.describe_patient(p)
    assert "an email is on file" in line and "sarah@example.com" not in line
    family = {**p, "records": [*p["records"], {"id": "K1", "name": "Lim Ethan", "email": ""}]}
    assert "email is on file" not in tools.describe_patient(family)        # not for everyone
