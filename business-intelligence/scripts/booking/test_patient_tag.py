"""POST /internal/patient-tag: the WhatsApp assistant adds an allowlisted
admin tag to a patient in Plato, keeping the tags already there."""
from __future__ import annotations

import pytest

from booking import app as app_mod

TOKEN = "t0k"


class FakePlato:
    def __init__(self, tags):
        self.patient = {"_id": "p1", "tag": [{"tag": t} for t in tags]}
        self.puts = []

    def get(self, path, params=None, **_):
        assert path == "/patient/p1"
        return self.patient

    def put(self, path, payload):
        self.puts.append((path, payload))
        return {}


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", TOKEN)
    fake = FakePlato(["Post-partum"])
    monkeypatch.setattr(app_mod, "plato", lambda: fake)
    return app_mod.app.test_client(), fake


def _tag(c, token=TOKEN, **body):
    return c.post("/internal/patient-tag", headers={"X-Internal-Token": token},
                  json={"patient_id": "p1", "tag": "Late change waiver used", **body})


def test_adds_the_tag_and_keeps_existing_ones(setup):
    c, fake = setup
    r = _tag(c)
    assert r.status_code == 200 and r.get_json()["added"] is True
    assert fake.puts == [("/patient/p1", {"tag": [{"tag": "Post-partum"},
                                                   {"tag": "Late change waiver used"}]})]


def test_already_tagged_is_a_no_op(setup):
    c, fake = setup
    fake.patient["tag"].append({"tag": "Late change waiver used"})
    assert _tag(c).get_json()["added"] is False and fake.puts == []


def test_dry_run_reads_but_never_writes(setup):
    c, fake = setup
    r = _tag(c, dry_run=True)
    assert r.get_json() == {"ok": True, "added": True, "dry_run": True} and fake.puts == []


def test_only_allowlisted_tags_and_a_valid_token(setup, monkeypatch):
    c, fake = setup
    assert _tag(c, tag="VIP").status_code == 400
    assert _tag(c, token="nope").status_code == 403
    assert _tag(c, patient_id="../x").status_code == 400
    monkeypatch.setattr(app_mod, "INTERNAL_TOKEN", "")
    assert _tag(c).status_code == 404
    assert fake.puts == []
