"""
Sync the website shop catalogue (`catalog.json`) to Stripe: one Product, one
Price and one Payment Link per enabled item. Phase 1 of the shop: the site's
/shop buttons go through the go.gojiphysio.com redirector (`pay` slugs in the
dashboard's LINK_SLUGS) to these Payment Links; the front desk enters each sale
into Plato by hand.

Idempotent, so re-run it after any catalogue edit:
  - Product id is fixed (`goji_<key>`): created once, then name/description kept
    in sync.
  - Prices are immutable in Stripe, so each amount gets its own Price, found by
    lookup_key `goji_<key>_<amount>`. Changing an amount creates a new Price.
  - A Payment Link is reused while it points at the current Price. When the
    Price changes, a new link is created and the old one is deactivated (not
    deleted; it can be re-enabled in Stripe).

Dry run by default; pass --apply to write. The key decides test vs live:
    read -s STRIPE_API_KEY && export STRIPE_API_KEY
    python3 stripe_catalog.py            # show the plan
    python3 stripe_catalog.py --apply    # write, then save shop_links.<mode>.json

A restricted key needs write on Products, Prices and Payment Links. Stdlib only.
Payment methods (PayNow, cards, wallets) follow the account's dashboard settings.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.stripe.com/v1"
HERE = Path(__file__).resolve().parent
SITE = "https://www.gojiphysio.com"

# Shown above the Pay button on every link.
SUBMIT_MESSAGE = (
    "By paying you agree to Goji's shop terms (gojiphysio.com/terms). "
    "We'll WhatsApp you within one working day to arrange your first session "
    "or your collection."
)

# Checkout fields per item kind (Stripe allows up to 3). Phone and email are
# always collected, so these only cover what the front desk needs for Plato.
CUSTOM_FIELDS = {
    "package": [{"key": "attendee", "label": "Name of the person attending", "optional": False}],
    "voucher": [{"key": "recipient", "label": "Recipient's name", "optional": True}],
    "merch": [],
}


def _flatten(data, prefix=""):
    """Encode nested dicts/lists the way Stripe's form API expects (a[b][0]=c)."""
    out = []
    if isinstance(data, dict):
        for k, v in data.items():
            out += _flatten(v, f"{prefix}[{k}]" if prefix else k)
    elif isinstance(data, list):
        for i, v in enumerate(data):
            out += _flatten(v, f"{prefix}[{i}]")
    elif isinstance(data, bool):
        out.append((prefix, "true" if data else "false"))
    elif data is not None:
        out.append((prefix, str(data)))
    return out


class Stripe:
    def __init__(self, key: str):
        self.auth = "Basic " + base64.b64encode(f"{key}:".encode()).decode()

    def call(self, method: str, path: str, params: dict | None = None) -> dict:
        body = urllib.parse.urlencode(_flatten(params or {}))
        url = f"{API}{path}"
        data = None
        if method == "GET" and body:
            url += "?" + body
        elif body:
            data = body.encode()
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": self.auth})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            err = json.load(e)
            if e.code == 404:
                return {"_missing": True}
            raise SystemExit(f"Stripe {method} {path}: {err.get('error', {}).get('message', err)}")

    def payment_links(self) -> list[dict]:
        links, params = [], {"limit": 100, "active": True}
        while True:
            page = self.call("GET", "/payment_links", params)
            links += page["data"]
            if not page.get("has_more"):
                return links
            params["starting_after"] = page["data"][-1]["id"]


def price_params(item: dict, product_id: str) -> tuple[str, dict]:
    if "custom_amount" in item:
        ca = item["custom_amount"]
        lookup = f"goji_{item['key']}_custom_{ca['minimum']}_{ca['preset']}_{ca['maximum']}"
        return lookup, {"product": product_id, "currency": "sgd", "lookup_key": lookup,
                        "custom_unit_amount": {"enabled": True, **ca}}
    lookup = f"goji_{item['key']}_{item['amount']}"
    return lookup, {"product": product_id, "currency": "sgd", "lookup_key": lookup,
                    "unit_amount": item["amount"]}


def link_params(item: dict, price_id: str) -> dict:
    p = {
        "line_items": [{"price": price_id, "quantity": 1}],
        "phone_number_collection": {"enabled": True},
        "custom_fields": [
            {"key": f["key"], "label": {"type": "custom", "custom": f["label"]},
             "type": "text", "optional": f["optional"]}
            for f in CUSTOM_FIELDS[item["kind"]]
        ],
        "custom_text": {"submit": {"message": SUBMIT_MESSAGE}},
        "after_completion": {"type": "redirect",
                             "redirect": {"url": f"{SITE}/shop/thanks/?item={item['key']}"}},
        "metadata": {"goji_key": item["key"], "goji_price": price_id},
    }
    if item["kind"] == "merch" and item.get("stock"):
        # The link closes itself once this many orders are paid.
        p["restrictions"] = {"completed_sessions": {"limit": item["stock"]}}
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write to Stripe (default: dry run)")
    args = ap.parse_args()

    key = os.environ.get("STRIPE_API_KEY", "")
    if not key:
        sys.exit("Set STRIPE_API_KEY first (see the docstring).")
    mode = "live" if "_live_" in key else "test"
    items = [i for i in json.loads((HERE / "catalog.json").read_text())["items"]
             if i.get("enabled", True)]
    if mode == "live" and (inferred := [i["key"] for i in items if i.get("inferred")]):
        print(f"Live key: skipping unconfirmed prices ({', '.join(inferred)}). "
              "Confirm them and drop `inferred` from catalog.json.\n")
        items = [i for i in items if not i.get("inferred")]

    s = Stripe(key)
    existing_links = s.payment_links()
    urls: dict[str, str] = {}
    print(f"Stripe {mode} mode, {'APPLY' if args.apply else 'dry run'}\n")

    for item in items:
        k = item["key"]
        product_id = f"goji_{k.replace('-', '_')}"
        product = {"name": item["name"], "description": item["description"],
                   "metadata": {"goji_key": k}}
        got = s.call("GET", f"/products/{product_id}")
        if got.get("_missing"):
            print(f"{k}: create product")
            if args.apply:
                s.call("POST", "/products", {"id": product_id, **product})
        elif got["name"] != item["name"] or got.get("description") != item["description"]:
            print(f"{k}: update product")
            if args.apply:
                s.call("POST", f"/products/{product_id}", product)

        lookup, pp = price_params(item, product_id)
        found = s.call("GET", "/prices", {"lookup_keys": [lookup], "active": True})["data"]
        price_id = found[0]["id"] if found else None
        if not price_id:
            print(f"{k}: create price {lookup}")
            if args.apply:
                price_id = s.call("POST", "/prices", pp)["id"]

        mine = [l for l in existing_links if l.get("metadata", {}).get("goji_key") == k]
        current = next((l for l in mine if l["metadata"].get("goji_price") == price_id), None)
        if current:
            urls[k] = current["url"]
        else:
            print(f"{k}: create payment link")
            if args.apply:
                urls[k] = s.call("POST", "/payment_links", link_params(item, price_id))["url"]
        for old in mine:
            if old is not current:
                print(f"{k}: deactivate old link {old['url']}")
                if args.apply:
                    s.call("POST", f"/payment_links/{old['id']}", {"active": False})

    print()
    for k, u in urls.items():
        print(f"{k:14} {u}")
    if args.apply:
        out = HERE / f"shop_links.{mode}.json"
        out.write_text(json.dumps(urls, indent=2) + "\n")
        print(f"\nSaved {out.name}")


if __name__ == "__main__":
    main()
