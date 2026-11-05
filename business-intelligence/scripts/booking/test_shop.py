"""Unit tests for shop fulfilment (stub Stripe + Plato: no network, no writes)."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from booking import shop


def session(livemode=False, paid=True, pi_meta=None, plato_item=None, phone="+6591234567"):
    return {
        "id": f"cs_{'live' if livemode else 'test'}_abc123",
        "mode": "payment", "livemode": livemode,
        "payment_status": "paid" if paid else "unpaid",
        "amount_total": 2000,
        "payment_intent": {"id": "pi_123", "metadata": pi_meta or {}},
        "customer_details": {"name": "Jane Tan", "email": "Jane@Example.com", "phone": phone},
        "custom_fields": [],
        "line_items": {"data": [{
            "description": "Goji Girl Socks (Grip)", "quantity": 1, "amount_total": 2000,
            "price": {"lookup_key": "goji_socks-girl-grip_2000",
                      "product": {"name": "Goji Girl Socks (Grip)",
                                  "metadata": {"goji_key": "socks-girl-grip",
                                               **({"plato_item": plato_item} if plato_item else {})}}},
        }]},
    }


class StubStripe:
    def __init__(self, sess):
        self.sess = sess
        self.tagged = []

    def session(self, sid):
        return self.sess

    def tag_payment(self, pi, inv):
        self.tagged.append((pi, inv))
        self.sess["payment_intent"]["metadata"]["plato_invoice_id"] = inv


class StubPlato:
    def __init__(self, patients=None, swap_doctor=None):
        self.patients = patients or {}
        self.searches, self.posts, self.puts = [], [], []
        self.doctor = None
        self.swap_doctor = swap_doctor  # mimic Plato replacing an unknown code

    def get(self, path, params=None):
        if path == "invoice":
            return {"data": [{"doctor": self.doctor}]}
        self.searches.append(params)
        for v in params.values():
            if v in self.patients:
                return {"data": self.patients[v]}
        return {"data": []}

    def post(self, path, payload):
        self.posts.append((path, payload))
        if path == "invoice":
            self.doctor = self.swap_doctor or payload.get("doctor")
        return {"_id": "pat_new" if path == "patient" else "inv_1"}

    def put(self, path, payload):
        self.puts.append((path, payload))
        if not self.swap_doctor:
            self.doctor = payload.get("doctor")
        return {"success": True}


@pytest.fixture
def live_writes(monkeypatch):
    monkeypatch.setenv("SHOP_PLATO_DRY_RUN", "0")
    monkeypatch.setenv("SHOP_PLATO_DOCTOR", "PCL")


def test_dry_run_is_the_default_and_writes_nothing(monkeypatch):
    monkeypatch.delenv("SHOP_PLATO_DRY_RUN", raising=False)
    plato = StubPlato()
    out = shop.fulfil("cs_test_abc123", plato, StubStripe(session()))
    assert out["status"] == "dry_run" and plato.posts == []
    assert out["plan"]["payment"] == {"mode": "Stripe", "amount": 20.0, "ref": "pi_123"}


def test_test_mode_always_bills_the_test_patient(live_writes):
    plato = StubPlato({"ZZ Goji Shop Test": [{"_id": "pat_test", "name": "ZZ Goji Shop Test"}],
                       "91234567": [{"_id": "pat_real", "name": "Jane Tan"}]})
    out = shop.fulfil("cs_test_abc123", plato, StubStripe(session()))
    assert out["status"] == "invoiced"
    inv = dict(plato.posts)["invoice"]
    assert inv["patient_id"] == "pat_test"          # not Jane, even though her phone matches
    assert "TEST mode" in inv["notes"] and inv["location"] == "SG" and inv["doctor"] == "PCL"


def test_live_matches_phone_and_writes_invoice_payment_finalize(live_writes):
    plato = StubPlato({"91234567": [{"_id": "pat_real", "name": "Jane Tan"}]})
    stripe = StubStripe(session(livemode=True))
    out = shop.fulfil("cs_live_abc123", plato, stripe)
    assert [p for p, _ in plato.posts] == ["invoice", "invoice/items_others", "invoice/payment", "invoice/finalize"]
    assert dict(plato.posts)["invoice"]["patient_id"] == "pat_real"
    other = dict(plato.posts)["invoice/items_others"]["items"][0]
    assert other["name"] == "Goji Girl Socks (Grip)" and other["selling_price"] == 20.0
    assert stripe.tagged == [("pi_123", "inv_1")] and out["patient_match"] == "phone"


def test_mapped_item_goes_on_the_invoice(live_writes):
    plato = StubPlato({"91234567": [{"_id": "pat_real"}]})
    shop.fulfil("cs_live_abc123", plato, StubStripe(session(livemode=True, plato_item="SOCK-G")))
    assert dict(plato.posts)["invoice"]["items"] == [{"given_id": "SOCK-G", "qty": 1, "selling_price": 20.0}]
    assert "invoice/items_others" not in dict(plato.posts)


def test_unknown_buyer_gets_a_new_patient(live_writes):
    plato = StubPlato()
    shop.fulfil("cs_live_abc123", plato, StubStripe(session(livemode=True)))
    assert plato.posts[0] == ("patient", {"name": "Jane Tan", "telephone": "91234567",
                                          "email": "jane@example.com"})
    assert dict(plato.posts)["invoice"]["patient_id"] == "pat_new"


def test_second_call_is_a_no_op(live_writes):
    plato = StubPlato({"91234567": [{"_id": "pat_real"}]})
    stripe = StubStripe(session(livemode=True))
    shop.fulfil("cs_live_abc123", plato, stripe)
    n = len(plato.posts)
    again = shop.fulfil("cs_live_abc123", plato, stripe)
    assert again["status"] == "already" and len(plato.posts) == n


def test_unpaid_session_writes_nothing(live_writes):
    plato = StubPlato()
    out = shop.fulfil("cs_test_abc123", plato, StubStripe(session(paid=False)))
    assert out["status"] == "unpaid" and plato.posts == []


def test_bad_session_id_rejected():
    with pytest.raises(shop.ShopError):
        shop.fulfil("not-a-session", StubPlato(), StubStripe(session()))


def test_local_phone():
    assert shop.local_phone("+65 9123 4567") == "91234567"
    assert shop.local_phone("+44 7700 900123") == "447700900123"


def test_webhook_signature():
    payload = json.dumps({"type": "x"}).encode()
    t = 1_800_000_000
    sig = hmac.new(b"whsec_x", f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    assert shop.verify_webhook(payload, f"t={t},v1={sig}", "whsec_x", now=t)
    assert not shop.verify_webhook(payload, f"t={t},v1={sig}", "whsec_other", now=t)
    assert not shop.verify_webhook(payload, f"t={t},v1={sig}", "whsec_x", now=t + 3600)


def test_real_write_needs_a_doctor(live_writes, monkeypatch):
    monkeypatch.delenv("SHOP_PLATO_DOCTOR")
    plato = StubPlato({"91234567": [{"_id": "pat_real"}]})
    with pytest.raises(shop.ShopError) as e:
        shop.fulfil("cs_live_abc123", plato, StubStripe(session(livemode=True)))
    assert e.value.code == "config" and plato.posts == []


def test_swapped_doctor_stops_before_payment(live_writes):
    plato = StubPlato({"91234567": [{"_id": "pat_real"}]}, swap_doctor="PCN")
    with pytest.raises(shop.ShopError) as e:
        shop.fulfil("cs_live_abc123", plato, StubStripe(session(livemode=True)))
    assert e.value.code == "plato_doctor"
    assert [p for p, _ in plato.posts] == ["invoice"]      # no payment, no finalise
    assert plato.puts == [("invoice", {"invoice_id": "inv_1", "doctor": "PCL"})]
