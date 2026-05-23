# Plato API - Webhooks

Source: https://clinic.platomedical.com/developers/1.0/webhooks
Captured: 2026-05-23

---

Webhooks allow you to receive semi-real-time notifications when specific events occur in your Plato Medical database. This enables you to build integrations that react to changes in patients, appointments, and invoices automatically.

## Overview

When events occur in Plato (such as a patient being created or an appointment being modified), webhooks queue these events and send them to your configured endpoint via HTTP POST requests.

## Important notes

- **Only user actions trigger webhooks.** Actions made via the API will NOT trigger webhooks. This is deliberate to avoid infinite loops.
- **Max 5 webhooks per database.** Any number of events can be associated with each webhook endpoint. This limit cannot be increased.
- **Events are batched** and sent together. There may be a few seconds delay.
- **Endpoint must respond HTTP 200 within 3 seconds.** Keep handlers lightweight; process async.
- Always have an alternative sync path (e.g. `modified_since` API polling) in case the webhook endpoint is down.
- Webhook events are NOT stored on Plato's end. Plato support cannot troubleshoot webhook delivery.
- For inventory and corporate webhooks, only single-record actions trigger events; bulk actions do not.

## Supported events

| Event | Trigger |
|---|---|
| `patient:upsert`     | Patient created or updated |
| `patient:merge`      | Two patients merged (payload includes `from_id`, `to_id`) |
| `appointment:upsert` | Appointment created or updated |
| `appointment:delete` | Appointment deleted |
| `invoice:upsert`     | Invoice created/updated, including payment changes. Draft invoices can fire this multiple times before finalization. |
| `invoice:finalize`   | Draft invoice finalized (fires once per invoice) |
| `invoice:delete`     | Draft invoice deleted (only drafts can be deleted; finalized invoices never) |
| `inventory:upsert`   | Single inventory item created/updated (not bulk) |
| `inventory:delete`   | Single inventory item deleted (not bulk) |
| `corporate:upsert`   | Single corporate record created/updated (not bulk) |
| `corporate:delete`   | Single corporate record deleted (not bulk) |
| `webhook:token`      | Sent once on webhook registration; required to activate |

### Example event payload

```json
{
  "events": [
    {
      "db": "databasename",
      "event": "appointment:upsert",
      "on": 1769346352,
      "object_type": "appointment",
      "object_id": "0eec101a220748758b8d33550ad236fa"
    }
  ]
}
```

Fields per event:

- `db` (string, required) - database identifier
- `event` (string, required) - event type
- `on` (integer, required) - Unix timestamp of the event
- `object_type` (string, optional)
- `object_id` (string, optional)
- Additional fields per event type (e.g. `from_id`/`to_id` for `patient:merge`, `given_id` for inventory/corporate)

## Setting up a webhook

### Step 1: Register

`POST /{db}/webhook`:

```json
{
  "url": "https://your-server.com/webhook_receive",
  "events": ["patient:upsert", "appointment:upsert"],
  "notification_email": "admin@yourcompany.com"
}
```

- `url` must be HTTPS
- `events` array must contain only approved event types
- `notification_email` must be valid

A `webhook:token` event is immediately POSTed to your URL.

### Step 2: Receive token

Your endpoint receives:

```json
{
  "events": [{
    "db": "databasename",
    "event": "webhook:token",
    "on": 1769346352,
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }]
}
```

### Step 3: Activate

`POST /{db}/webhook/activate`:

```json
{ "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." }
```

Note: users currently logged into Plato will need to re-login for the webhook to take effect.

## Managing webhooks

- List: `GET /{db}/webhook`
- Delete: `DELETE /{db}/webhook/{webhook_id}`

## Batching

- Events grouped by URL and database
- Up to 500 events per batch
- Multiple batches may be sent concurrently

## Failure handling

- Automatic retry up to 3 times
- 50ms delay between retries
- 3-second timeout per request
- Email notification on failure
- **If a webhook fails 5 times within 24 hours, it is automatically removed.** You'll need to set it up again.

## Best practices

- **Idempotency:** the same event may be sent multiple times.
- **Fast response:** respond within 3 seconds. Process events asynchronously.
- **Error handling:** return 2xx if you received the request, even if internal processing fails.
- **Security:** validate the `db` field matches your database identifier.
- **Monitoring:** monitor your endpoint for failures.

## Authentication

All webhook management endpoints require:

```
Authorization: Bearer YOUR_API_TOKEN
```

---

## Notes for Goji BI

- Hourly polling with `modified_since` is the baseline. Webhooks are an optional upgrade for sub-minute freshness on appointments/invoices.
- A natural Cloud Run setup: a single `POST /webhook` HTTPS endpoint that just enqueues events to Pub/Sub or writes directly to a BigQuery `raw_plato.webhook_events` table, then returns 200 within 3 seconds.
- We are limited to 5 webhook URLs total. One catch-all endpoint subscribed to all events we care about is the right pattern.
- Plan to back webhook reception with the polling job - never trust webhooks alone for accuracy of financial data.
