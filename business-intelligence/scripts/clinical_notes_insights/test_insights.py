"""Codebook, suppression, pacing and window tests on synthetic notes only."""
from datetime import date, datetime, timezone

import pytest

import insights as ci


def labels(*notes: str) -> dict[str, set[str]]:
    return ci.derive([(f"2026-01-{i + 1:02d}", t) for i, t in enumerate(notes)])


@pytest.mark.parametrize("text,bucket", [
    ("6 weeks postpartum, SVD", "6-12 weeks"),
    ("PP 3wks, LSCS", "under 6 weeks"),
    ("4 months post-natal", "3-6 months"),
    ("6/52 PP", "6-12 weeks"),
    ("3/12 postnatal", "3-6 months"),
    ("baby is 9 months old", "6-12 months"),
    ("18 months postpartum", "1 year+"),
])
def test_weeks_postpartum(text, bucket):
    assert labels(text)["weeks postpartum at first visit"] == {bucket}


def test_postpartum_timing_uses_first_note_only():
    f = labels("Initial: back pain", "now 8 weeks postpartum")
    assert f["weeks postpartum at first visit"] == set()
    assert f["postpartum"] == {"yes"}


@pytest.mark.parametrize("text,tri", [
    ("24 weeks pregnant", "2nd"),
    ("GA 31", "3rd"),
    ("12/40", "1st"),
    ("second trimester, PGP", "2nd"),
])
def test_trimester(text, tri):
    assert labels(text)["trimester at first visit"] == {tri}


def test_birth_types():
    assert labels("EMCS after failed forceps")["birth type mentioned"] == {"c-section", "instrumental"}
    assert labels("SVD")["birth type mentioned"] == {"vaginal"}
    assert labels("enjoys vacuuming")["birth type mentioned"] == set()


@pytest.mark.parametrize("text,yes", [
    ("SUI with coughing", True),
    ("leaking when running", True),
    ("no leaking", False),
    ("denies urgency or leakage", False),
    ("Leaking: nil", False),
    ("breast milk leaking", False),
])
def test_leaking_negation(text, yes):
    assert (labels(text)["leaking/urgency reported"] == {"yes"}) is yes


def test_diastasis_needs_a_measurement():
    assert labels("DRA 2fw above umbilicus")["diastasis measured"] == {"yes"}
    assert labels("2.5cm gap at umbilicus")["diastasis measured"] == {"yes"}
    assert labels("asked about diastasis")["diastasis measured"] == set()


def test_pain_locations_with_negation():
    f = labels("R wrist pain (de Quervain's), no neck pain. LBP on lifting")
    assert f["pain location"] == {"wrist/thumb", "back"}


def test_goals_read_only_after_goal_intro():
    f = labels("Runs 5km weekly before pregnancy. Goals: lift baby without pain, return to gym")
    assert f["main goal"] == {"lifting/carrying baby", "exercise/sport"}
    assert labels("Runs 5km weekly")["goal recorded"] == set()


def test_report_suppresses_small_cells():
    pp = {"weeks postpartum at first visit": {"6-12 weeks"}, "trimester at first visit": set(),
          "postpartum": {"yes"}, "birth type mentioned": {"c-section"},
          "leaking/urgency reported": {"yes"}, "diastasis measured": set(),
          "pain location": set(), "goal recorded": set(), "main goal": set(),
          "active-ageing goal": set()}
    people = {f"p{i}": {k: set(v) for k, v in pp.items()} for i in range(6)}
    people["p0"]["diastasis measured"] = {"yes"}
    out = ci.report(people, ages=None)
    assert "Patients with notes: 6" in out
    leak = next(l for l in out.splitlines() if l.strip().startswith("yes") and "100" in l)
    assert leak.split()[1] == "6"
    assert any(l.split()[:2] == ["yes", "<5"] and len(l.split()) == 2 for l in out.splitlines())
    assert "active-ageing" not in out  # needs ages


def test_report_hides_breakdown_for_small_groups():
    f = labels("Goals: balance and strength")
    out = ci.report({"p1": f}, ages={"p1": 70})
    assert "Aged 60+ (from Plato DOB): <5" in out
    assert "balance" not in out


def test_age_on():
    assert ci.age_on("1960-10-28", date(2026, 10, 27)) == 65
    assert ci.age_on("0000-00-00", date(2026, 10, 27)) is None
    assert ci.age_on(None, date(2026, 10, 27)) is None


@pytest.mark.parametrize("hh,mm,ok", [(23, 0, True), (2, 0, True), (5, 30, True), (5, 31, False), (21, 0, False)])
def test_run_window(hh, mm, ok):
    sgt = datetime(2026, 10, 27, hh, mm, tzinfo=ci.SGT)
    assert ci.in_window(sgt.astimezone(timezone.utc)) is ok


def test_html_note_text():
    assert "leaking" in ci.to_text("<p>Mild&nbsp;leaking</p><br>")


class FakeResp:
    def __init__(self, status, body=None, remaining="19"):
        self.status_code, self._body = status, body
        self.headers = {"x-ratelimit-remaining": remaining}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.headers, self.calls = list(responses), {}, 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return self.responses.pop(0)


def plato(responses):
    sleeps = []
    t = [0.0]
    p = ci.Plato("db", "k", session=FakeSession(responses), sleep=sleeps.append, clock=lambda: t[0])
    return p, sleeps


def test_pacing_and_low_remaining():
    p, sleeps = plato([FakeResp(200, [], "19"), FakeResp(200, [], "3")])
    p.get("/x")
    p.get("/x")
    assert sleeps == [ci.REQUEST_INTERVAL_S, 60]


def test_stops_after_three_429s():
    p, sleeps = plato([FakeResp(429)] * 3)
    with pytest.raises(ci.PlatoError, match="429"):
        p.get("/x")
    assert sleeps.count(ci.BACKOFF_429_S) == 2


def test_pages_stop_on_short_page_and_repeat():
    full = [{"_id": str(i)} for i in range(ci.PAGE_SIZE)]
    p, _ = plato([FakeResp(200, full), FakeResp(200, full[:3])])
    assert sum(len(b) for b in p.pages("/x")) == ci.PAGE_SIZE + 3
    p, _ = plato([FakeResp(200, full), FakeResp(200, full)])
    with pytest.raises(ci.PlatoError, match="repeats"):
        list(p.pages("/x"))


def test_parse_errors_name_the_field_not_the_value():
    f = ci.Fields("patient_id", "created_at", "note")
    with pytest.raises(ci.PlatoError) as e:
        f.parse({"patient_id": "p1", "body": "SECRET TEXT"}, "page 1")
    assert "'note'" in str(e.value) and "SECRET" not in str(e.value)
