# Website shop (Phase 1)

Packages, gift vouchers and merch sold on gojiphysio.com/shop through Stripe
Payment Links. Each paid order becomes a finalised Plato invoice automatically:

    /shop Buy button → go.gojiphysio.com/web-pay-<item> (logs the click)
      → Stripe Payment Link (?client_reference_id=<click id>)
      → /shop/thanks/?session_id=cs_… → booking service POST /api/shop/confirm
      → Plato: find/create patient, invoice, Stripe payment, finalise
      (Stripe's webhook → POST /api/stripe/webhook does the same if the buyer
       closes the tab; whichever lands first invoices it, once.)

Code: `scripts/booking/shop.py`. Items with `plato_item` in `catalog.json` bill
that Plato inventory code; others go on as a named "other" line. Writes are off
until `SHOP_PLATO_DRY_RUN=0`; test-mode orders always bill the Plato patient
"ZZ Goji Shop Test", whatever the buyer typed.

## Testing checkout locally (Stripe test mode)
1. `~/.goji-shop-test.env` (chmod 600) holds `STRIPE_API_KEY=sk_test_…` and
   `PLATO_API_KEY=…`.
2. `SHOP_SITE=http://localhost:4234 python3 stripe_catalog.py --apply` with the
   test key creates test links (`shop_links.test.json`); put them in the env file
   as `PUBLIC_SHOP_TEST_LINKS='{"socks-girl-grip": "https://buy.stripe.com/test_…"}'`.
3. Start the `shop-test-booking` and `shop-test-site` previews
   (`.claude/launch.json`), open http://localhost:4234/shop/, buy with card
   4242 4242 4242 4242. The thanks page shows the result (`dry_run` / `invoiced`).

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
1. Check the order's Plato invoice (remarks: "Website shop order cs_…"). If the
   patient match says "several matches: check", confirm it's the right patient.
2. If there is no invoice (Plato was down), enter it by hand: invoice the item,
   payment mode **Stripe** with the payment id as the reference, finalise.
3. WhatsApp the buyer within one working day to book (or send the voucher code).
