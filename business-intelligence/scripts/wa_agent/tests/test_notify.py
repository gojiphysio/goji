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
