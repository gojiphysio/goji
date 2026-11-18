import hashlib
import hmac

from wa_agent.whatsapp import Echo, Inbound, Status, WhatsAppClient, parse_webhook, verify_signature

from .payloads import echo, inbound, status


def sign(body: bytes, secret="test-secret"):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_signature_must_match_and_fails_closed():
    body = b'{"a":1}'
    assert verify_signature(body, sign(body), "test-secret")
    assert not verify_signature(body, sign(b'{"a":2}'), "test-secret")
    assert not verify_signature(body, None, "test-secret")
    assert not verify_signature(body, sign(body), "")  # no secret configured


def test_parse_inbound_with_name():
    [ev] = parse_webhook(inbound())
    assert isinstance(ev, Inbound)
    assert (ev.wa_id, ev.text, ev.name, ev.kind) == ("6591234567", "What are your hours?",
                                                     "Mei Ling", "text")


def test_non_text_becomes_placeholder():
    [ev] = parse_webhook(inbound(kind="audio"))
    assert ev.text == "[sent a voice note]" and ev.kind == "audio"


def test_parse_echo_is_keyed_on_the_customer():
    [ev] = parse_webhook(echo())
    assert isinstance(ev, Echo)
    assert ev.wa_id == "6591234567" and ev.text == "Hi! Chris here"


def test_parse_status():
    [ev] = parse_webhook(status())
    assert isinstance(ev, Status) and ev.status == "delivered"


def test_unknown_fields_ignored():
    body = {"entry": [{"changes": [{"field": "history", "value": {"x": 1}}]}]}
    assert parse_webhook(body) == []


class _Http:
    def __init__(self):
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers))
        from types import SimpleNamespace as NS
        payload = {"messages": [{"id": "wamid.out"}]}
        return NS(raise_for_status=lambda: None, content=b"x", json=lambda: payload)


def test_send_uses_configured_transport():
    http = _Http()
    c = WhatsAppClient(base="https://waba.example.io", phone_number_id="123", token="tok",
                       send_path="/messages", auth_header="D360-API-KEY", auth_prefix="",
                       session=http)
    assert c.send_text("6591234567", "hi") == "wamid.out"
    url, body, headers = http.calls[0]
    assert url == "https://waba.example.io/messages"
    assert headers["D360-API-KEY"] == "tok"
    assert body["to"] == "6591234567" and body["text"]["body"] == "hi"


def test_default_meta_path_includes_phone_number_id():
    c = WhatsAppClient(base="https://graph.facebook.com/v23.0", phone_number_id="pnid",
                       token="t", session=_Http())
    assert c.url == "https://graph.facebook.com/v23.0/pnid/messages"
    assert c.headers["Authorization"] == "Bearer t"
