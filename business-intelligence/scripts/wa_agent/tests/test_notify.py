import logging

from wa_agent import config, notify


def _send_draft(caplog):
    with caplog.at_level(logging.INFO, logger=notify.log.name):
        notify.send("drafted", customer="Ana", wa_id="6590000000",
                    staff_note="wants a Saturday", suggested_reply="Hi Ana!",
                    reason="intent:other", last_message="any sat?")
    return caplog.text


def test_local_run_without_smtp_logs_the_draft(monkeypatch, caplog):
    monkeypatch.setattr(config, "GMAIL_APP_PASSWORD", "")
    monkeypatch.setattr(config, "STATE_BACKEND", "memory")
    assert "Hi Ana!" in _send_draft(caplog)


def test_deployed_run_without_smtp_logs_subject_only(monkeypatch, caplog):
    # Cloud Run logs must not carry message text.
    monkeypatch.setattr(config, "GMAIL_APP_PASSWORD", "")
    monkeypatch.setattr(config, "STATE_BACKEND", "firestore")
    text = _send_draft(caplog)
    assert "no SMTP configured" in text and "Hi Ana!" not in text



def test_a_handover_ping_shows_what_the_customer_got_and_the_draft_apart():
    body = notify.compose("escalated", customer="Ana", wa_id="65", staff_note="MC",
                          suggested_reply="Yes, we can issue an MC [confirm].",
                          sent_reply="The team will get back to you today.",
                          reason="intent:other", last_message="MC pls").get_content()
    assert body.index("The customer got:") < body.index("The team will get back")
    assert "NOT sent; fill in anything in [brackets]" in body
    assert "Agent sent this holding reply" not in body and "24 hours" not in body
