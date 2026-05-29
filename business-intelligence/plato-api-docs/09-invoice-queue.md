# Plato API - Invoice / Queue

Source: https://clinic.platomedical.com/developers/1.0/invoice_queue
Captured: 2026-05-23

---

This guide covers the core invoice and queue workflow: add patient to queue, add invoice items, finalize invoice, record payment, update queue status.

> **Invoice and Queue Entry are synonymous in Plato.** Every queue entry corresponds to an invoice, and vice versa.

## 1) Add patient to queue / create invoice

`POST /{db}/invoice`

Creates a draft invoice (and queue entry) for a patient. You can optionally include items and payments in the same call.

```bash
curl -X POST "https://clinic.platomedical.com/api/DATABASENAME/invoice" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "5861de8b2e564783f313a4b2174bdb2a",
    "doctor": "DT",
    "location": "ME",
    "session": 0,
    "date": "2026-03-14"
  }'
```

## 2) Add items to existing invoice

`POST /{db}/invoice/items`

Use this to add or replace invoice items. The `given_id` in each item must match an item in Inventory Setup. Set `method` to `append` or `replace`.

```bash
curl -X POST "https://clinic.platomedical.com/api/DATABASENAME/invoice/items" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "65372cc7250104712d7b05306b5a438b",
    "method": "append",
    "items": [
      { "given_id": "CON", "qty": 1 },
      { "given_id": "ARC-120", "qty": 10, "dosage": "Take 2 tab/s daily for 3 days" }
    ]
  }'
```

## 3) Finalize invoice

`POST /{db}/invoice/finalize`

Finalizes a draft invoice. Once finalized, the invoice cannot be amended through the API.

```bash
curl -X POST "https://clinic.platomedical.com/api/DATABASENAME/invoice/finalize" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{ "invoice_id": "65372cc7250104712d7b05306b5a438b" }'
```

## 4) Record payment

`POST /{db}/invoice/payment`

```bash
curl -X POST "https://clinic.platomedical.com/api/DATABASENAME/invoice/payment" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "65372cc7250104712d7b05306b5a438b",
    "mode": "Cash",
    "amount": 100.00,
    "ref": ""
  }'
```

## 5) Change queue/invoice status

`POST /{db}/queue/status`

```bash
curl -X POST "https://clinic.platomedical.com/api/DATABASENAME/queue/status" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "5861de8b2e564783f313a4b2174bdb2a",
    "status_id": "NUgq"
  }'
```

## Recommended sequence

1. Create draft queue/invoice using `POST /{db}/invoice`
2. Add billable items using `POST /{db}/invoice/items`
3. Finalize invoice using `POST /{db}/invoice/finalize`
4. Record payment using `POST /{db}/invoice/payment`
5. Update queue status using `POST /{db}/queue/status`

---

## Notes for Goji BI

- Key BI insight: **invoice IS the queue entry**. So a single invoice fetch gives us both the financial side (items, total, payments) and the operational side (queue status, doctor, location, session).
- `doctor` and `location` are coded IDs (e.g. `DT`, `ME`). We'll need to pull `/systemsetup` to resolve them into human names for dimensions.
- `given_id` on invoice items maps to inventory codes - this is our `dim_service` join key. Need a one-time inventory pull plus periodic refresh.
- For reporting we only need GET endpoints; the POST endpoints here are for write-back automations we may add later (e.g. auto-create invoice when an appointment is marked attended).
