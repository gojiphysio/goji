# Plato API - Endpoint Reference (Swagger)

Source: https://clinic.platomedical.com/api/api/documentation
Live Swagger JSON: https://clinic.platomedical.com/swagger/api.json?basePath=/api/
Captured: 2026-05-23

Base URL: `/api/`
All paths use the convention `/{db}/...` where `{db}` is the clinic's database identifier.

---

## adjustment

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/adjustment` | List adjustments |
| POST   | `/{db}/adjustment` | Create adjustment |
| GET    | `/{db}/adjustment/{adjustment_id}` | Get adjustment |
| PUT    | `/{db}/adjustment/{adjustment_id}` | Update adjustment |
| DELETE | `/{db}/adjustment/{adjustment_id}` | Delete adjustment |
| GET    | `/{db}/adjustment/count` | Count adjustments |

## appointment

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/appointment` | List appointments |
| POST   | `/{db}/appointment` | Create appointment |
| GET    | `/{db}/appointment/{appointment_id}` | Get appointment |
| PUT    | `/{db}/appointment/{appointment_id}` | Update appointment |
| DELETE | `/{db}/appointment/{appointment_id}` | Delete appointment |
| GET    | `/{db}/appointment/{appointment_id}/prereg` | Get pre-registration link |
| GET    | `/{db}/appointment/count` | Count appointments |
| GET    | `/{db}/appointment/calendars` | List calendars |
| GET    | `/{db}/appointment/codes` | List appointment codes |
| POST   | `/{db}/appointment/slots` | Get available slots |
| GET    | `/{db}/onlineapptbooking/list` | List online booking calendars |
| GET    | `/{db}/onlineapptbooking/slots` | Get online booking slots |

## communication

| Method | Path | Purpose |
|---|---|---|
| GET  | `/{db}/whatsapp/settings` | WhatsApp settings |
| POST | `/{db}/whatsapp/send` | Send WhatsApp message |
| GET  | `/{db}/whatsapp/list` | List WhatsApp messages |

## contact

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/contact` | List contacts |
| POST   | `/{db}/contact` | Create contact |
| GET    | `/{db}/contact/{contact_id}` | Get contact |
| PUT    | `/{db}/contact/{contact_id}` | Update contact |
| DELETE | `/{db}/contact/{contact_id}` | Delete contact |
| GET    | `/{db}/contact/count` | Count contacts |

## corporate

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/corporate` | List corporates |
| POST   | `/{db}/corporate` | Create corporate |
| GET    | `/{db}/corporate/{corporate_id}` | Get corporate |
| PUT    | `/{db}/corporate/{corporate_id}` | Update corporate |
| DELETE | `/{db}/corporate/{corporate_id}` | Delete corporate |
| GET    | `/{db}/corporate/count` | Count corporates |

## deliveryorder

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/deliveryorder` | List delivery orders |
| POST   | `/{db}/deliveryorder` | Create delivery order |
| GET    | `/{db}/deliveryorder/{deliveryorder_id}` | Get delivery order |
| PUT    | `/{db}/deliveryorder/{deliveryorder_id}` | Update delivery order |
| DELETE | `/{db}/deliveryorder/{deliveryorder_id}` | Delete delivery order |
| GET    | `/{db}/deliveryorder/count` | Count delivery orders |

## expense

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/expense` | List expenses |
| POST   | `/{db}/expense` | Create expense |
| GET    | `/{db}/expense/{expense_id}` | Get expense |
| PUT    | `/{db}/expense/{expense_id}` | Update expense |
| DELETE | `/{db}/expense/{expense_id}` | Delete expense |
| GET    | `/{db}/expense/count` | Count expenses |

## facility

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/facility` | List facilities |
| POST   | `/{db}/facility` | Create facility |
| GET    | `/{db}/facility/{facility_id}` | Get facility |
| PUT    | `/{db}/facility/{facility_id}` | Update facility |
| DELETE | `/{db}/facility/{facility_id}` | Delete facility |
| GET    | `/{db}/facility/count` | Count facilities |

## graphing

| Method | Path | Purpose |
|---|---|---|
| GET | `/{db}/patient/{patient_id}/graphing` | Patient graphing data |
| GET | `/{db}/patient/graphing/count` | Graphing count |

## inventory

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/inventory` | List inventory |
| POST   | `/{db}/inventory` | Create inventory item |
| GET    | `/{db}/inventory/{inventory_id}` | Get inventory item |
| PUT    | `/{db}/inventory/{inventory_id}` | Update inventory item |
| DELETE | `/{db}/inventory/{inventory_id}` | Delete inventory item |
| GET    | `/{db}/inventory/count` | Count inventory items |

## invoice / queue

| Method | Path | Purpose |
|---|---|---|
| GET  | `/{db}/invoice` | List invoices |
| POST | `/{db}/invoice` | Create invoice / add to queue |
| PUT  | `/{db}/invoice` | Update invoice/queue fields |
| GET  | `/{db}/invoice/count` | Count invoices |
| POST | `/{db}/invoice/items` | Add items to invoice |
| POST | `/{db}/invoice/items_others` | Add other items |
| POST | `/{db}/invoice/payment` | Record payment |
| POST | `/{db}/invoice/bill_to_corporate` | Bill to corporate |
| POST | `/{db}/invoice/finalize` | Finalize invoice |
| GET  | `/{db}/queue` | Queue list for a day |
| POST | `/{db}/queue` | Add patient to queue |
| GET  | `/{db}/queue/status/list` | List queue statuses |
| POST | `/{db}/queue/status` | Change queue status |
| GET  | `/{db}/queue/status` | Get queue statuses for an invoice |

## platopay

| Method | Path | Purpose |
|---|---|---|
| GET  | `/{db}/platopay/accounts` | List PlatoPay accounts |
| GET  | `/{db}/platopay/invoice_link` | Invoice payment link |
| GET  | `/{db}/platopay/cards` | List stored cards |
| GET  | `/{db}/platopay/add_card_link` | Add-card link |
| POST | `/{db}/platopay/charge_card` | Charge stored card |

## letter

| Method | Path | Purpose |
|---|---|---|
| GET | `/{db}/letter` | List letters |
| GET | `/{db}/letter/count` | Count letters |

## patient

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/patient` | List patients |
| POST   | `/{db}/patient` | Create patient |
| GET    | `/{db}/patient/{patient_id}` | Get patient |
| PUT    | `/{db}/patient/{patient_id}` | Update patient |
| DELETE | `/{db}/patient/{patient_id}` | Delete patient |
| GET    | `/{db}/patient/{patient_id}/updatelink` | Patient self-update URL |
| POST   | `/{db}/patient/merge` | Merge two patients |
| GET    | `/{db}/patient/count` | Count patients |

## patient_note

| Method | Path | Purpose |
|---|---|---|
| GET  | `/{db}/patient/{patient_id}/note` | Get all notes for a patient |
| GET  | `/{db}/patient/note` | List all notes |
| POST | `/{db}/patient/note` | Create note |
| GET  | `/{db}/patient/note/count` | Count notes |

## payment

| Method | Path | Purpose |
|---|---|---|
| GET | `/{db}/payment` | List payments |
| GET | `/{db}/payment/count` | Count payments |

## purchaseorder

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/purchaseorder` | List POs |
| POST   | `/{db}/purchaseorder` | Create PO |
| GET    | `/{db}/purchaseorder/{purchaseorder_id}` | Get PO |
| PUT    | `/{db}/purchaseorder/{purchaseorder_id}` | Update PO |
| DELETE | `/{db}/purchaseorder/{purchaseorder_id}` | Delete PO |
| GET    | `/{db}/purchaseorder/count` | Count POs |

## purchaserequisition

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/purchaserequisition` | List PRs |
| POST   | `/{db}/purchaserequisition` | Create PR |
| GET    | `/{db}/purchaserequisition/{purchaserequisition_id}` | Get PR |
| PUT    | `/{db}/purchaserequisition/{purchaserequisition_id}` | Update PR |
| DELETE | `/{db}/purchaserequisition/{purchaserequisition_id}` | Delete PR |
| GET    | `/{db}/purchaserequisition/count` | Count PRs |

## reports

| Method | Path | Purpose |
|---|---|---|
| GET | `/{db}/reports/outstanding` | Outstanding invoices as-of a date |
| GET | `/{db}/reports/stock_count` | Stock count as-of a date |
| GET | `/{db}/reports/stock_count_detailed` | Detailed stock count |
| GET | `/{db}/reports/outstanding_packages` | Outstanding package items per patient |

## search

| Method | Path | Purpose |
|---|---|---|
| GET | `/{db}/search/supplier` | Search suppliers |
| GET | `/{db}/search/contact` | Search contacts |
| GET | `/{db}/search/facility` | Search facilities |
| GET | `/{db}/search/corporate` | Search corporates |
| GET | `/{db}/search/inventory` | Search inventory |
| GET | `/{db}/search/patient` | Search patients |

## supplier

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/supplier` | List suppliers |
| POST   | `/{db}/supplier` | Create supplier |
| GET    | `/{db}/supplier/{supplier_id}` | Get supplier |
| PUT    | `/{db}/supplier/{supplier_id}` | Update supplier |
| DELETE | `/{db}/supplier/{supplier_id}` | Delete supplier |
| GET    | `/{db}/supplier/count` | Count suppliers |

## task

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/task` | List tasks |
| POST   | `/{db}/task` | Create task |
| GET    | `/{db}/task/{task_id}` | Get task |
| PUT    | `/{db}/task/{task_id}` | Update task |
| DELETE | `/{db}/task/{task_id}` | Delete task |
| GET    | `/{db}/task/count` | Count tasks |

## transfer

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/transfer` | List transfers |
| POST   | `/{db}/transfer` | Create transfer |
| GET    | `/{db}/transfer/{transfer_id}` | Get transfer |
| PUT    | `/{db}/transfer/{transfer_id}` | Update transfer |
| DELETE | `/{db}/transfer/{transfer_id}` | Delete transfer |
| GET    | `/{db}/transfer/count` | Count transfers |

## systemsetup

| Method | Path | Purpose |
|---|---|---|
| GET | `/{db}/systemsetup` | Get all configuration settings |

## webhook

| Method | Path | Purpose |
|---|---|---|
| GET    | `/{db}/webhook` | List webhooks |
| POST   | `/{db}/webhook` | Register webhook |
| POST   | `/{db}/webhook/activate` | Activate webhook |
| DELETE | `/{db}/webhook/{webhook_id}` | Delete webhook |

---

## Endpoints we need for Goji BI

**Phase 1 (core BI):**

- `GET /{db}/systemsetup` - resolves doctor codes, location codes, calendar IDs, queue statuses (refresh daily)
- `GET /{db}/appointment` + `appointment/codes` + `appointment/calendars` - feeds `fct_appointment` and `dim_service`
- `GET /{db}/invoice` - feeds `fct_invoice`
- `GET /{db}/payment` - feeds `fct_payment`
- `GET /{db}/queue/status/list` + `GET /{db}/queue` - feeds queue status dimension and current-day operational view
- `GET /{db}/patient` - feeds `dim_patient` (with PII handling - probably only store hashed_id, age_band, postcode prefix, gender)
- `GET /{db}/inventory` - feeds `dim_service` (the catalogue of billable items)

**Phase 2 (additional context):**

- `GET /{db}/corporate` - third-party payers (insurance, workers comp)
- `GET /{db}/contact` - referring doctors / clinics for acquisition source analysis
- `GET /{db}/reports/outstanding` - shortcut for AR aging if we don't want to compute it ourselves
- `GET /{db}/adjustment` - for refunds and write-offs
- `GET /{db}/expense` - if we want clinic expenses inside the warehouse rather than only via Xero

**Pull strategy:**

For every list endpoint above, paginate via `current_page` with `modified_since` filter for incremental syncs. Detail endpoints are only needed if list returns insufficient fields.
