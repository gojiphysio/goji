from types import SimpleNamespace as NS

from booking import config as booking_config
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
    assert out["url"] == ("https://go.gojiphysio.com/wa-book?"
                          "service=physiotherapy&focus=womens-health")


def test_bad_service_is_an_error_result_not_an_exception():
    out, err = tools.run_tool("booking_link", {"service": "massage"}, wa_id="x")
    assert err and "unknown service" in out


class _Http:
    def __init__(self, status=200, payload=None):
        self.status, self.payload, self.calls = status, payload or {}, []

    def get(self, url, params, timeout):
        self.calls.append((url, params))
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

    def get(self, url, params, timeout):
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
