"""Doctor referrals: a referrer's photo is read and the patient's name and
number go to Chris; the agent never replies to the referrer."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace as NS

import pytest

from wa_agent import app as app_mod
from wa_agent import config, events, notify, referral
from wa_agent.state import MemoryStore

from .fakes import FakeClaude, FakeWhatsApp
from .payloads import inbound

DOCTOR = "6580000001"
CHRIS = "6590000009"


def said(patients, doctor=""):
    body = json.dumps({"patients": patients, "doctor": doctor})
    return NS(stop_reason="end_turn", model="m", usage=None,
              content=[NS(type="text", text=body)])


def photo(msg_id="wamid.p1", caption="", ts=None):
    p = inbound(wa_id=DOCTOR, msg_id=msg_id, kind="image", name="Ong",
                ts=ts or int(time.time()))
    msg = p["entry"][0]["changes"][0]["value"]["messages"][0]
    msg["image"]["mime_type"] = "image/jpeg"
    if caption:
        msg["image"]["caption"] = caption
    return p


@pytest.fixture
def env(monkeypatch):
    rec, notes, templates = [], [], []
    st = MemoryStore()
    wa = FakeWhatsApp()
    wa.media = (b"\xff\xd8jpeg", "image/jpeg")
    wa.send_template = lambda n, name, params, language="en": (
        templates.append((n, name, params)) or "wamid.tpl")
    monkeypatch.setattr(app_mod, "store", st)
    monkeypatch.setattr(app_mod, "wa", wa)
    monkeypatch.setattr(app_mod, "claude", FakeClaude())
    monkeypatch.setattr(app_mod, "_submit", lambda fn, *a: fn(*a))
    monkeypatch.setattr(app_mod, "_sleep", lambda s: None)
    monkeypatch.setattr(config, "REFERRERS", {DOCTOR: "Dr Ong"})
    monkeypatch.setattr(config, "REFERRAL_TO", (CHRIS,))
    monkeypatch.setattr(config, "STAFF", frozenset({CHRIS}))
    monkeypatch.setattr(events, "record", lambda e, w, **f: rec.append((e, f)) or {})
    monkeypatch.setattr(notify, "send", lambda kind, **kw: notes.append((kind, kw)))
    st.note_staff_inbound(CHRIS, time.time())  # Chris's 24h window is open
    return NS(st=st, wa=wa, rec=rec, notes=notes, templates=templates)


def run(payload):
    from wa_agent.whatsapp import parse_webhook
    for ev in parse_webhook(payload):
        app_mod.handle_inbound(ev, time.time())


def test_photo_is_forwarded_to_chris(env):
    app_mod.claude.queue.append(said([{"name": "Lim Mei Ling", "phone": "+65 9123-4567"}],
                                     doctor="Dr Lim"))
    run(photo(caption="has insurance"))
    assert env.wa.sent == [(CHRIS, "New referral from Dr Ong:\nName: Lim Mei Ling\n"
                                   "HP: 9123 4567\nDoctor: Dr Lim\nNote: has insurance")]
    req = app_mod.claude.requests[0]
    assert req["messages"][0]["content"][0]["type"] == "image"


def test_agent_never_replies_to_the_referrer(env):
    run(inbound(wa_id=DOCTOR, text="Hi Chris, sending one over"))
    assert env.wa.sent == [] and app_mod.claude.requests == []
    assert env.st.load(DOCTOR).history[-1]["text"] == "Hi Chris, sending one over"


def test_second_photo_of_same_patient_is_not_sent_twice(env):
    p = [{"name": "Lim Mei Ling", "phone": "91234567"}]
    app_mod.claude.queue += [said(p), said(p)]
    run(photo("wamid.p1"))
    run(photo("wamid.p2", caption="has insurance"))
    assert [t for _, t in env.wa.sent] == [
        "New referral from Dr Ong:\nName: Lim Mei Ling\nHP: 9123 4567",
        'Dr Ong also sent a photo: "has insurance"']


def test_insurance_card_right_after_a_referral_only_adds_its_caption(env):
    app_mod.claude.queue += [said([{"name": "Tan", "phone": "91234567"}]), said([])]
    run(photo("wamid.p1"))
    run(photo("wamid.p2", caption="has insurance"))
    assert env.wa.sent[1] == (CHRIS, 'Dr Ong also sent a photo: "has insurance"')


def test_unreadable_photo_tells_chris_to_look(env):
    app_mod.claude.queue.append(said([]))
    run(photo())
    assert "couldn't find a patient's name and number" in env.wa.sent[0][1]


def test_model_failure_tells_chris_to_look(env):
    app_mod.claude.queue.append(RuntimeError("overloaded"))
    run(photo())
    assert "couldn't find" in env.wa.sent[0][1]
    assert ("referral_failed", {"reason": "RuntimeError"}) in env.rec


def test_window_shut_sends_template_and_holds_details_until_chris_writes(env, monkeypatch):
    monkeypatch.setattr(env.st, "get_staff_windows", lambda: {})
    app_mod.claude.queue.append(said([{"name": "Tan", "phone": "91234567"}]))
    run(photo())
    assert env.wa.sent == []
    (number, name, params), = env.templates
    assert number == CHRIS and name == config.STAFF_TEMPLATE
    assert "91234567" not in " ".join(params) and "Ong" in params[0]
    run(inbound(wa_id=CHRIS, msg_id="wamid.c1", text="status"))
    assert env.wa.sent[0] == (CHRIS, "New referral from Dr Ong:\nName: Tan\nHP: 9123 4567")
    assert env.st.pop_held_referrals(CHRIS) == []


def test_forward_failure_emails(env):
    env.wa.fail = True
    app_mod.claude.queue.append(said([{"name": "Tan", "phone": "91234567"}]))
    run(photo())
    assert env.notes and env.notes[0][0] == "escalated"


def test_referrer_reaction_is_ignored(env, monkeypatch):
    monkeypatch.setattr(app_mod, "_customer_reaction", lambda ev: pytest.fail("pinged"))
    p = inbound(wa_id=DOCTOR, kind="reaction")
    p["entry"][0]["changes"][0]["value"]["messages"][0]["reaction"] = {
        "message_id": "wamid.x", "emoji": "😡"}
    run(p)


@pytest.mark.parametrize("raw,want", [
    ("9123 4567", "6591234567"), ("+65-9123-4567", "6591234567"), ("6561234567", "6561234567"),
    ("", ""), ("12", ""), ("+44 7700 900123", "447700900123")])
def test_normalise_phone(raw, want):
    assert referral.normalise_phone(raw) == want


def test_parse_tolerates_prose_and_junk():
    assert referral.parse('Here you go: {"patients": [{"name": " Tan  Ah Kow ", '
                          '"phone": "9123 4567"}], "doctor": "Dr Lim"}') == {
        "patients": [{"name": "Tan Ah Kow", "phone": "6591234567"}], "doctor": "Dr Lim"}
    assert referral.parse("no json") == {"patients": [], "doctor": ""}


def test_media_block_refuses_other_files():
    assert referral.media_block(b"x", "video/mp4") is None
    assert referral.media_block(b"%PDF", "application/pdf")["type"] == "document"


def test_referrers_env_parsing():
    assert config._referrers("6580000001=Dr Ong, 6580000002") == {
        "6580000001": "Dr Ong", "6580000002": "a referring doctor"}
