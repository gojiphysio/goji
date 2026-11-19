from wa_agent import config, learning
from wa_agent.policy import ChatState


def test_draft_outcome_labels():
    draft = "Hi Anna! Our physio session is $260 for 55 minutes."
    assert learning.draft_outcome(draft, draft.upper() + "  ")[1] == "sent_unchanged"
    assert learning.draft_outcome(draft, "Hi Anna, our physio session is $260 nett "
                                         "for 55 mins :)")[1] == "edited"
    assert learning.draft_outcome(draft, "Let me check with Cheryl and revert!")[1] == "replaced"


def test_echo_after_draft_scores_the_draft_and_clears_it():
    s = ChatState(wa_id="1", pending_draft={"text": "hi", "intent": "booking", "at": 100.0})
    sig = learning.classify_echo(s, 200.0)
    assert sig["intent"] == "booking" and sig["_draft_text"] == "hi" and s.pending_draft == {}


def test_echo_after_auto_send_is_a_rescue_once():
    s = ChatState(wa_id="1", last_auto={"intent": "pricing", "at": 100.0})
    assert learning.classify_echo(s, 200.0) == {"intent": "pricing", "rescue": True}
    assert learning.classify_echo(s, 300.0) == {}


def test_old_signals_expire():
    s = ChatState(wa_id="1", last_auto={"intent": "pricing", "at": 0.0})
    assert learning.classify_echo(s, learning.RESCUE_WINDOW_S + 1) == {}


def test_three_rescues_in_window_demote_and_only_a_person_promotes():
    a = {}
    for i in range(10):
        learning.note_auto_send(a, "pricing", f"m{i}")
    assert not learning.note_rescue(a, "pricing")
    assert not learning.note_rescue(a, "pricing")
    assert learning.note_rescue(a, "pricing")       # third rescue demotes
    assert not learning.note_rescue(a, "pricing")   # already demoted: no repeat alert
    base = {"pricing": "auto", "faq": "auto", "urgent": "escalate"}
    eff = learning.effective_policy(base, a)
    assert eff == {"pricing": "draft", "faq": "auto", "urgent": "escalate"}
    learning.promote(a, "pricing")
    assert learning.effective_policy(base, a)["pricing"] == "auto"


def test_rescues_age_out_of_the_window():
    a = {}
    for _ in range(2):
        learning.note_auto_send(a, "faq", "m")
        learning.note_rescue(a, "faq")
    for _ in range(learning.DEMOTE_WINDOW):
        learning.note_auto_send(a, "faq", "m")
    assert not learning.note_rescue(a, "faq")       # the old two fell out


def test_feedback_links_are_signed(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "https://wa.example")
    monkeypatch.setattr(config, "FEEDBACK_SECRET", "k")
    links = learning.feedback_links("0123456789abcdef", 1700)
    assert links["up"].startswith("https://wa.example/feedback?c=0123456789abcdef&t=1700&r=up&s=")
    sig = links["up"].rsplit("s=", 1)[1]
    assert learning.feedback_valid("0123456789abcdef", "1700", "up", sig)
    assert not learning.feedback_valid("0123456789abcdef", "1700", "down", sig)
    assert not learning.feedback_valid("0123456789abcdeX", "1700", "up", sig)


def test_no_links_without_public_url(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "")
    assert learning.feedback_links("0123456789abcdef", 1) == {}
