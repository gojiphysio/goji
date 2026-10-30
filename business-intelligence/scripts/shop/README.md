# Website shop (Phase 1)

Packages and gift vouchers sold on gojiphysio.com/shop through Stripe Payment
Links. No server of our own: the flow is

    /shop Buy button → go.gojiphysio.com/web-pay-<item> (logs the click)
      → Stripe Payment Link (?client_reference_id=<click id>)
      → /shop/thanks → front desk enters the sale into Plato by hand

## Changing the catalogue
1. Edit `catalog.json` (amounts in SGD cents) and `marketing/website/src/lib/shop.ts`.
2. `read -s STRIPE_API_KEY && export STRIPE_API_KEY` (a test key first), then
   `python3 stripe_catalog.py` to see the plan and `--apply` to write it.
3. Copy the URLs from `shop_links.live.json` into `SHOP_PAY_URLS` in
   `scripts/dashboard/app.py`, and add any new item's `web-pay-<key>` slug to
   `LINK_SLUGS` there and to `CtaSlug` in the site's `src/lib/links.ts`.

A live key skips any item still marked `inferred`. Use `/usr/bin/python3`:
the python.org build has no CA certificates and fails the TLS handshake.

## Front desk, for each Stripe sale email
1. Find or create the patient in Plato (match on phone).
2. Invoice the matching package item, record the payment as **Stripe**, finalise.
   The session balance then shows on the Package Alerts tab.
3. WhatsApp the buyer within one working day to book (or send the voucher code).
