# Plato API - PlatoPay

Source: https://clinic.platomedical.com/developers/1.0/platopay
Captured: 2026-05-23

---

This guide explains the PlatoPay endpoints for payment links, card-on-file flows, and charging stored cards.

## Overview

PlatoPay is configured in Plato under System Setup -> PlatoPay Setup. The API exposes endpoints to:

- List available PlatoPay accounts
- Generate invoice payment links
- Generate add-card links for patients
- List stored cards for a patient
- Charge a stored card

## 1) Get PlatoPay accounts

```bash
curl -X GET "https://clinic.platomedical.com/api/DATABASENAME/platopay/accounts" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx"
```

Use the returned account ID as `acct_id` in other PlatoPay calls.

## 2) Generate invoice payment link

```bash
curl -X GET "https://clinic.platomedical.com/api/DATABASENAME/platopay/invoice_link?invoice_id=5861de8b2e564783f313a4b2174bdb2a&acct_id=acct_4ertldkfghkdjh&amount=10.00" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx"
```

Query params:

- `invoice_id`: invoice identifier
- `acct_id`: PlatoPay account ID
- `amount`: payment amount

## 3) Generate add-card link

```bash
curl -X GET "https://clinic.platomedical.com/api/DATABASENAME/platopay/add_card_link?patient_id=388b7792e324ce2559ee6d3add4d414e" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx"
```

## 4) List stored cards

```bash
curl -X GET "https://clinic.platomedical.com/api/DATABASENAME/platopay/cards?patient_id=388b7792e324ce2559ee6d3add4d414e" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx"
```

You'll need the returned `card_id` to charge a stored card.

## 5) Charge a stored card

**CAUTION:** This endpoint affects the flow of funds. Include proper authorization, validation, and retry handling.

```bash
curl -X POST "https://clinic.platomedical.com/api/DATABASENAME/platopay/charge_card" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "5861de8b2e564783f313a4b2174bdb2a",
    "acct_id": "acct_4ertldkfghkdjh",
    "card_id": "card_sdklfhjkwewer",
    "amount": 10.00
  }'
```

## Suggested integration flow

1. Call `/{db}/platopay/accounts` and choose an `acct_id`.
2. For pay-by-link: call `/{db}/platopay/invoice_link` and send the URL to the patient.
3. For card-on-file: call `/{db}/platopay/add_card_link`, then list cards with `/{db}/platopay/cards`.
4. Charge stored cards using `/{db}/platopay/charge_card`.

## Authentication

All PlatoPay endpoints require bearer-token authentication.

---

## Notes for Goji BI

- For pure BI/reporting, we do NOT touch the charge endpoint. We only need to **read** the resulting payments via the invoice/payment data.
- PlatoPay account configuration is one-time setup; not relevant for the data pipeline.
- If we later add a "send payment link" automation (e.g. auto-send link 24h after appointment), it's a small Cloud Run job that reads from BQ and calls `invoice_link`.
