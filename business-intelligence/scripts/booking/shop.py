"""
Website shop fulfilment: a paid Stripe Checkout Session becomes a finalised
Plato invoice, so online sales sit in Plato beside in-clinic ones (one patient
record, one revenue ledger for the dashboards and the Cash Book P&L).

    /shop cart -> POST /api/shop/checkout -> Stripe Checkout (all cart lines)
      -> /shop/thanks/?session_id=cs_...
      thanks page -> POST /api/shop/confirm      } both call fulfil(); the
      Stripe      -> POST /api/stripe/webhook    } first one wins, once

fulfil() always re-reads the session from Stripe, so nothing a browser sends is
trusted. It is idempotent: the Plato invoice id is written to the PaymentIntent's
metadata (`plato_invoice_id`) and checked first, under a per-session lock (the
service runs one instance, one worker).

Plato mapping (POST /invoice, items_others if any, /invoice/payment, /finalize):
  - patient: matched on phone, then email; created if neither matches.
  - items: a Stripe Product with metadata `plato_item` (set from catalog.json by
    scripts/shop/stripe_catalog.py) bills that Plato inventory item; one without
    it is billed as a named "other" line at the paid price.
  - payment: mode SHOP_PLATO_PAYMENT_MODE ("Stripe"), ref = PaymentIntent id.

Safety switches (env):
  SHOP_PLATO_DRY_RUN  default "1": read Plato, log every write, write nothing.
  SHOP_TEST_PATIENT   name of the Plato patient every test-mode (livemode=false)
                      order is billed to, whatever the buyer typed. Default
                      "ZZ Goji Shop Test".
  SHOP_PLATO_DOCTOR   Plato requires a doctor code on every invoice ("Invalid
                      payload" without one, verified 2026-11-05); it decides whose
                      revenue the sale counts as. Required for real writes.
  SHOP_PLATO_LOCATION default "SG", the clinic's only location.

Verified against live Plato 2026-11-05 (test invoices #1231, #1232): payment
mode "Stripe" is accepted; `remarks` is silently dropped, `notes` is kept; and an
unknown doctor code is NOT rejected but silently replaced with a clinician (it
billed #1232 to PCN), so the doctor is read back and checked after every create.
The Online Shop doctor is code SHP (#1233 kept it).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger("booking.shop")

STRIPE_API = "https://api.stripe.com/v1"
SGT = timezone(timedelta(hours=8))
PAYMENT_MODE = os.environ.get("SHOP_PLATO_PAYMENT_MODE", "Stripe")
TEST_PATIENT = os.environ.get("SHOP_TEST_PATIENT", "ZZ Goji Shop Test")
WEBHOOK_TOLERANCE_S = 300
PRICE_CACHE_S = 300
MAX_QTY = 10
VOUCHER_MIN, VOUCHER_MAX = 50, 2000  # SGD, same bounds as the voucher Payment Link
SUBMIT_MESSAGE = ("By paying you agree to Goji's shop terms (gojiphysio.com/terms). "
                  "We'll WhatsApp you within one working day to arrange your sessions, "
                  "voucher or collection.")
_price_cache: tuple[float, dict] | None = None

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class ShopError(Exception):
    def __init__(self, msg: str, code: str = "error"):
        super().__init__(msg)
        self.code = code


def dry_run() -> bool:
    return os.environ.get("SHOP_PLATO_DRY_RUN", "1").lower() not in ("0", "false", "no")


# --- Stripe -----------------------------------------------------------------

class StripeClient:
    def __init__(self, key: str | None = None, timeout: int = 15):
        key = key or os.environ.get("STRIPE_API_KEY")
        if not key:
            raise ShopError("STRIPE_API_KEY not set", "config")
        self.s = requests.Session()
        self.s.auth = (key, "")
        self.timeout = timeout

    def session(self, session_id: str) -> dict:
        r = self.s.get(f"{STRIPE_API}/checkout/sessions/{session_id}",
                       params=[("expand[]", "line_items.data.price.product"),
                               ("expand[]", "payment_intent")],
                       timeout=self.timeout)
        if r.status_code == 404:
            raise ShopError("unknown checkout session", "not_found")
        r.raise_for_status()
        return r.json()

    def prices(self) -> dict[str, dict]:
        """goji key -> its current fixed Price (from the products stripe_catalog.py
        syncs). Cached briefly: the cart prices from Stripe, never the browser."""
        global _price_cache
        if _price_cache and time.monotonic() - _price_cache[0] < PRICE_CACHE_S:
            return _price_cache[1]
        out: dict[str, dict] = {}
        params: list[tuple[str, str]] = [("active", "true"), ("limit", "100"), ("expand[]", "data.product")]
        while True:
            r = self.s.get(f"{STRIPE_API}/prices", params=params, timeout=self.timeout)
            r.raise_for_status()
            page = r.json()
            for pr in page["data"]:
                prod = pr.get("product") or {}
                key = (prod.get("metadata") or {}).get("goji_key") if isinstance(prod, dict) else None
                # Stripe lists newest first: the first fixed price per key is current
                # (an old price stays active after an amount change).
                if key and prod.get("active", True) and pr.get("unit_amount") is not None \
                        and pr.get("currency") == "sgd" and not (out.get(key) or {}).get("price"):
                    out[key] = {"price": pr["id"], "amount": pr["unit_amount"], "product": prod["id"],
                                "name": prod.get("name")}
                elif key and prod.get("active", True) and pr.get("custom_unit_amount"):
                    out.setdefault(key, {"price": None, "amount": None, "product": prod["id"],
                                         "name": prod.get("name")})
            if not page.get("has_more"):
                break
            params = [p for p in params if p[0] != "starting_after"] + [("starting_after", page["data"][-1]["id"])]
        _price_cache = (time.monotonic(), out)
        return out

    def create_session(self, params: list[tuple[str, str]]) -> dict:
        r = self.s.post(f"{STRIPE_API}/checkout/sessions", data=params, timeout=self.timeout)
        if r.status_code >= 400:
            raise ShopError(f"Stripe checkout create failed: {r.text[:300]}", "stripe")
        return r.json()

    def tag_payment(self, payment_intent_id: str, invoice_id: str) -> None:
        r = self.s.post(f"{STRIPE_API}/payment_intents/{payment_intent_id}",
                        data={"metadata[plato_invoice_id]": invoice_id},
                        timeout=self.timeout)
        r.raise_for_status()


def verify_webhook(payload: bytes, sig_header: str, secret: str,
                   now: float | None = None) -> bool:
    """Stripe-Signature check (t=..., v1=...), HMAC-SHA256 over "t.payload"."""
    pairs = [p.split("=", 1) for p in (sig_header or "").split(",") if "=" in p]
    t = next((v for k, v in pairs if k == "t"), None)
    sigs = [v for k, v in pairs if k == "v1"]
    if not t or not sigs:
        return False
    if abs((now or time.time()) - int(t)) > WEBHOOK_TOLERANCE_S:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in sigs)


# --- Mapping ----------------------------------------------------------------

def local_phone(phone: str | None) -> str:
    """+65 9123 4567 -> 91234567 (how the clinic keys patients in Plato)."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[2:] if digits.startswith("65") and len(digits) == 10 else digits


def order_from_session(sess: dict) -> dict:
    if sess.get("mode") != "payment":
        raise ShopError("not a payment session", "unsupported")
    pi = sess.get("payment_intent") or {}
    if isinstance(pi, str):
        pi = {"id": pi, "metadata": {}}
    cust = sess.get("customer_details") or {}
    fields = {f.get("key"): (f.get("text") or {}).get("value")
              for f in sess.get("custom_fields") or []}
    items = []
    for li in (sess.get("line_items") or {}).get("data", []):
        price = li.get("price") or {}
        product = price.get("product") or {}
        meta = product.get("metadata") or {} if isinstance(product, dict) else {}
        items.append({
            "name": li.get("description") or (product.get("name") if isinstance(product, dict) else ""),
            "qty": li.get("quantity") or 1,
            "amount": (li.get("amount_total") or 0) / 100,
            "plato_item": meta.get("plato_item") or None,
            "key": meta.get("goji_key") or price.get("lookup_key"),
        })
    return {
        "session_id": sess["id"],
        "livemode": bool(sess.get("livemode")),
        "paid": sess.get("payment_status") == "paid",
        "payment_intent": pi.get("id"),
        "plato_invoice_id": (pi.get("metadata") or {}).get("plato_invoice_id"),
        "total": (sess.get("amount_total") or 0) / 100,
        "name": cust.get("name") or "",
        "email": (cust.get("email") or "").strip().lower(),
        "phone": local_phone(cust.get("phone")),
        "attendee": fields.get("attendee") or fields.get("recipient") or "",
        "items": items,
    }


def invoice_payload(order: dict, patient_id: str) -> tuple[dict, list[dict], dict]:
    """(POST /invoice body, items_others list, payment). Mapped items go on the
    invoice; the rest are "other" lines at the paid price. The payment is added
    after every line is on, so it never exceeds the invoice total."""
    mapped = [{"given_id": i["plato_item"], "qty": i["qty"],
               "selling_price": round(i["amount"] / i["qty"], 2)}
              for i in order["items"] if i["plato_item"]]
    others = [{"given_id": f"SHOP-{(i['key'] or 'ITEM').upper()}"[:40], "name": i["name"],
               "qty": i["qty"], "category": "Others",
               "selling_price": round(i["amount"] / i["qty"], 2)}
              for i in order["items"] if not i["plato_item"]]
    tag = "" if order["livemode"] else " (Stripe TEST mode)"
    notes = f"Website shop order {order['session_id']}{tag}"
    if order["attendee"]:
        notes += f". Attending/recipient: {order['attendee']}"
    body = {
        "patient_id": patient_id,
        "date": datetime.now(SGT).strftime("%Y-%m-%d"),
        "invoice_notes": "Paid online (gojiphysio.com/shop)",
        "notes": notes,
        "location": os.environ.get("SHOP_PLATO_LOCATION", "SG"),
        "items": mapped,
    }
    payment = {"mode": PAYMENT_MODE, "amount": order["total"],
               "ref": order["payment_intent"] or order["session_id"]}
    if os.environ.get("SHOP_PLATO_DOCTOR"):
        body["doctor"] = os.environ["SHOP_PLATO_DOCTOR"]
    return body, others, payment


# --- Plato ------------------------------------------------------------------

def _rows(resp) -> list[dict]:
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        data = resp.get("data", resp.get("results"))
        if isinstance(data, list):
            return data
        if resp.get("_id"):
            return [resp]
    return []


def _search(plato, params: dict) -> list[dict]:
    try:
        return _rows(plato.get("search/patient", params))
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return []  # some Plato search endpoints answer "no match" with 404
        raise


def find_patient(plato, order: dict) -> tuple[str | None, str]:
    """(patient_id, how). Test-mode orders always resolve to the test patient."""
    if not order["livemode"]:
        rows = _search(plato, {"query": TEST_PATIENT})
        hit = next((r for r in rows if (r.get("name") or "").strip() == TEST_PATIENT), None)
        return (hit["_id"], "test patient") if hit else (None, "test patient (create)")
    if order["phone"]:
        rows = _search(plato, {"telephone": order["phone"]})
        if len(rows) > 1 and order["email"]:
            rows = [r for r in rows if (r.get("email") or "").strip().lower() == order["email"]] or rows
        if rows:
            return rows[0]["_id"], "phone" + (" (several matches: check)" if len(rows) > 1 else "")
    if order["email"]:
        rows = _search(plato, {"email": order["email"]})
        if rows:
            return rows[0]["_id"], "email"
    return None, "new patient"


def new_patient_body(order: dict) -> dict:
    if not order["livemode"]:
        return {"name": TEST_PATIENT, "notes": "Test patient for website shop checkouts. Not a real person."}
    return {"name": order["name"] or "Website shop customer", "telephone": order["phone"],
            "email": order["email"]}


def _invoice_doctor(plato, invoice_id: str) -> str | None:
    rows = _rows(plato.get("invoice", {"invoice_id": invoice_id, "include_drafts": "true"}))
    return rows[0].get("doctor") if rows else None


def _check_doctor(plato, invoice_id: str, want: str) -> None:
    """Plato swaps an unknown doctor code for a clinician without an error, which
    would credit a shop sale to them. Correct it, or stop before taking payment."""
    if _invoice_doctor(plato, invoice_id) == want:
        return
    plato.put("invoice", {"invoice_id": invoice_id, "doctor": want})
    got = _invoice_doctor(plato, invoice_id)
    if got != want:
        raise ShopError(f"Plato filed invoice {invoice_id} under doctor {got!r}, not {want!r}: "
                        f"is {want!r} a doctor code in Plato? Invoice left unpaid and unfinalised.",
                        "plato_doctor")


def checkout_params(cart: list[dict], prices: dict[str, dict], origin: str,
                    client_ref: str | None = None) -> list[tuple[str, str]]:
    """Stripe Checkout Session form params for a cart of {key, qty[, amount]}.
    Fixed-price items use their synced Price; a gift voucher carries the amount
    the buyer chose (SGD, bounded) as inline price_data on the voucher product."""
    if not cart or len(cart) > 20:
        raise ShopError("empty or oversized cart", "bad_request")
    params: list[tuple[str, str]] = [
        ("mode", "payment"),
        ("success_url", f"{origin}/shop/thanks/?session_id={{CHECKOUT_SESSION_ID}}"),
        ("cancel_url", f"{origin}/shop/"),
        ("phone_number_collection[enabled]", "true"),
        ("custom_text[submit][message]", SUBMIT_MESSAGE),
        ("payment_intent_data[description]", "Goji website shop"),
    ]
    if client_ref and re.fullmatch(r"[A-Za-z0-9_-]{1,200}", client_ref):
        params.append(("client_reference_id", client_ref))
    kinds = set()
    for n, line in enumerate(cart):
        key = str(line.get("key") or "")
        try:
            qty = int(line.get("qty", 1))
        except (TypeError, ValueError):
            qty = 0
        if not 1 <= qty <= MAX_QTY:
            raise ShopError(f"bad quantity for {key}", "bad_request")
        p = prices.get(key)
        if not p:
            raise ShopError(f"unknown item {key}", "bad_request")
        pre = f"line_items[{n}]"
        if p["price"]:
            params += [(f"{pre}[price]", p["price"]), (f"{pre}[quantity]", str(qty))]
        else:  # voucher: buyer-chosen amount
            try:
                amount = int(line.get("amount") or 0)
            except (TypeError, ValueError):
                amount = 0
            if not VOUCHER_MIN <= amount <= VOUCHER_MAX:
                raise ShopError("voucher amount out of range", "bad_request")
            params += [(f"{pre}[price_data][currency]", "sgd"),
                       (f"{pre}[price_data][product]", p["product"]),
                       (f"{pre}[price_data][unit_amount]", str(amount * 100)),
                       (f"{pre}[quantity]", str(qty))]
        kinds.add("voucher" if not p["price"] else ("package" if key.startswith(("pp-", "cpsc-")) else "merch"))
    # Up to 3 custom fields; only ask what the front desk needs for Plato.
    fields = []
    if "package" in kinds:
        fields.append(("attendee", "Name of the person attending", "false"))
    if "voucher" in kinds:
        fields.append(("recipient", "Voucher recipient's name", "true"))
    for i, (k, label, optional) in enumerate(fields):
        params += [(f"custom_fields[{i}][key]", k), (f"custom_fields[{i}][type]", "text"),
                   (f"custom_fields[{i}][label][type]", "custom"),
                   (f"custom_fields[{i}][label][custom]", label),
                   (f"custom_fields[{i}][optional]", optional)]
    return params


def create_checkout(cart: list[dict], origin: str, client_ref: str | None = None,
                    stripe: StripeClient | None = None) -> str:
    """Returns the Stripe Checkout URL for a cart."""
    stripe = stripe or StripeClient()
    sess = stripe.create_session(checkout_params(cart, stripe.prices(), origin, client_ref))
    log.info("shop checkout %s: %s", sess.get("id"), [(c.get("key"), c.get("qty")) for c in cart])
    return sess["url"]


def _lock(session_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(session_id, threading.Lock())


def fulfil(session_id: str, plato, stripe: StripeClient | None = None) -> dict:
    """Make sure a paid Checkout Session has its Plato invoice. Safe to call any
    number of times. Returns {status, ...}; status is one of
    already | invoiced | dry_run | unpaid."""
    if not re.fullmatch(r"cs_(test|live)_[A-Za-z0-9]+", session_id or ""):
        raise ShopError("bad session id", "bad_request")
    stripe = stripe or StripeClient()
    with _lock(session_id):
        order = order_from_session(stripe.session(session_id))
        base = {"session_id": session_id, "livemode": order["livemode"], "total": order["total"],
                "items": [i["name"] for i in order["items"]]}
        if not order["paid"]:
            return {**base, "status": "unpaid"}
        if order["plato_invoice_id"]:
            return {**base, "status": "already", "invoice_id": order["plato_invoice_id"]}

        patient_id, how = find_patient(plato, order)
        plan = {"patient_match": how}
        if dry_run():
            body, others, payment = invoice_payload(order, patient_id or "<new patient>")
            plan.update({"create_patient": None if patient_id else new_patient_body(order),
                         "invoice": body, "items_others": others,
                         "payment": payment, "finalize": True})
            log.info("shop DRY RUN %s: %s", session_id, plan)
            return {**base, "status": "dry_run", "plan": plan}

        if not os.environ.get("SHOP_PLATO_DOCTOR"):
            raise ShopError("SHOP_PLATO_DOCTOR not set (Plato rejects invoices without one)", "config")
        if not patient_id:
            created = plato.post("patient", new_patient_body(order))
            patient_id = created.get("_id") or (created.get("data") or {}).get("_id")
            if not patient_id:
                raise ShopError(f"Plato patient create returned no id: {created}", "plato")
        body, others, payment = invoice_payload(order, patient_id)
        inv = plato.post("invoice", body)
        invoice_id = inv.get("_id") or inv.get("invoice_id") or (inv.get("data") or {}).get("_id")
        if not invoice_id:
            raise ShopError(f"Plato invoice create returned no id: {inv}", "plato")
        _check_doctor(plato, invoice_id, body["doctor"])
        if others:
            plato.post("invoice/items_others", {"invoice_id": invoice_id, "method": "append", "items": others})
        plato.post("invoice/payment", {"invoice_id": invoice_id, **payment})
        plato.post("invoice/finalize", {"invoice_id": invoice_id})
        if order["payment_intent"]:
            stripe.tag_payment(order["payment_intent"], invoice_id)
        log.info("shop invoiced %s -> Plato invoice %s (%s)", session_id, invoice_id, how)
        return {**base, "status": "invoiced", "invoice_id": invoice_id, "patient_match": how}
