# API Reference — Odoo PO Kanban

**Base URL:** `/api/v1`  
**Format:** JSON (request + response)  
**Auth:** Webhook endpoint checks `X-Forwarded-For` against `WEBHOOK_ALLOWED_IPS` (env). All other endpoints are open.

---

## 1. Health

### `GET /health`
Liveness probe.

**Response**
```json
{ "status": "ok" }
```

---

## 2. Kanban Board

### `GET /po/board`
Returns all POs grouped into kanban columns.

**Query params**

| Param | Type | Required | Description |
|---|---|---|---|
| `project_id` | string | No | Filter cards by project |

**Response — `KanbanBoard`**
```json
{
  "columns": {
    "new":         [ PurchaseOrderOut, ... ],
    "in_review":   [ PurchaseOrderOut, ... ],
    "in_progress": [ PurchaseOrderOut, ... ],
    "done":        [ PurchaseOrderOut, ... ]
  }
}
```

---

### `GET /po`
Flat list of all POs.

**Query params**

| Param | Type | Required | Description |
|---|---|---|---|
| `project_id` | string | No | Filter by project |
| `status` | string | No | Filter by status (`new` / `in_review` / `in_progress` / `done`) |

**Response** — `PurchaseOrderOut[]`

---

### `GET /po/pending`
Shortcut for `GET /po?status=new`.

**Query params**

| Param | Type | Required |
|---|---|---|
| `project_id` | string | No |

**Response** — `PurchaseOrderOut[]`

---

### `PATCH /po/{id}/status`
Move a PO to a different kanban column.

**Path param:** `id` — local DB integer ID

**Request body**
```json
{ "status": "new" | "in_review" | "in_progress" | "done" }
```

**Response** — `PurchaseOrderOut`

**Errors**
- `404` PO not found
- `400` Invalid status value

---

### `DELETE /po/{id}`
Hard-delete a PO and all its nested line items, GRN receipts, and PRQ receipts.

**Path param:** `id` — local DB integer ID

**Response** — `204 No Content`

**Errors**
- `404` PO not found

---

### `POST /po/pending/{id}/process`
Assign work packages to a pending PO and advance it to `in_progress`.

**Path param:** `id` — local DB integer ID

**Request body**
```json
{ "wp_ids": ["WP-001", "WP-002"] }
```

**Response**
```json
{
  "accepted": true,
  "row_id": 12,
  "status": "in_progress",
  "wp_ids": ["WP-001", "WP-002"]
}
```

**Errors**
- `404` PO not found
- `409` PO already in progress
- `400` PO already done / no work packages provided

---

## 3. Odoo Webhook (inbound)

### `POST /odoo/po-webhook`
Odoo pushes a purchase order payload here. The PO is immediately upserted into the local DB, then Odoo JSON-RPC enrichment runs in the background (non-blocking).

**IP restriction:** Caller IP must be in `WEBHOOK_ALLOWED_IPS` env var (comma-separated). If the var is empty, all IPs are allowed.

**Request body** — Odoo raw PO payload (JSON). Accepted fields:

| Field | Notes |
|---|---|
| `id` / `_id` | Odoo numeric PO ID |
| `display_name` / `name` | PO reference string, e.g. `PO/2024/00123` |
| `partner_id` | `[id, "Vendor Name"]` or plain string |
| `project_id` | `[id, "Project Name"]` or plain string |
| `package_id` | `[id, "Package Name"]` or plain string |
| `subject` | free-text description |
| `category` | category label |

**Response — `WebhookAck`**
```json
{
  "accepted": true,
  "po_id": 42,
  "created": true,
  "message": "PO created on kanban",
  "extracted": {
    "display_name": "PO/2024/00123",
    "partner_id": "Helios Supplies",
    "project_id": "Rajasthan 50MW",
    "package_id": "PKG-SOLAR-01",
    "subject": "Inverters and combiner boxes",
    "category": "Electrical"
  }
}
```

`created: false` when an existing PO was updated instead of created.

**Errors**
- `403` IP not in allow-list
- `500` Processing failure (details in `detail`)

---

## 4. Odoo Sync

### `POST /odoo/pull`
Pull the latest confirmed POs from Odoo into the kanban. Each PO is upserted and fully enriched with line items synchronously.

**Query params**

| Param | Type | Default | Range | Description |
|---|---|---|---|---|
| `limit` | int | 3 | 1–200 | Max POs to pull |

**Response**
```json
{
  "status": "ok",
  "created": 2,
  "updated": 1,
  "failed": [],
  "total": 3
}
```

**Errors**
- `502` Odoo unreachable or returned no data

---

### `POST /po/{id}/sync`
Re-sync a single PO from Odoo. Overwrites enrichment fields and line items. PO must already exist locally with an `odoo_id`.

**Path param:** `id` — local DB integer ID

**Response** — `PurchaseOrderOut` (fully enriched)

**Errors**
- `404` PO not found locally
- `422` PO has no `odoo_id`
- `502` Odoo unreachable

---

### `POST /po/{id}/fetch-grn`
Fetch GRN (stock receipts) from Odoo for the PO. Replaces all previously stored GRN records.

**Constraint:** PO must have `status = in_progress`.

**Path param:** `id` — local DB integer ID

**Response** — `GRNReceiptOut[]`
```json
[
  {
    "id": 1,
    "odoo_picking_id": 55,
    "name": "WH/IN/00012",
    "state": "done",
    "scheduled_date": "2024-11-01",
    "date_done": "2024-11-03"
  }
]
```

**Errors**
- `404` PO not found
- `422` PO is not in `in_progress` status / PO has no `odoo_id`
- `502` No GRN receipts found in Odoo

---

### `POST /po/{id}/fetch-prq`
Fetch PRQ (vendor bills / purchase invoices) from Odoo for the PO. Replaces all previously stored PRQ records.

**Constraint:** PO must have `status = done`.

**Path param:** `id` — local DB integer ID

**Response** — `PRQReceiptOut[]`
```json
[
  {
    "id": 1,
    "odoo_invoice_id": 88,
    "name": "BILL/2024/00012",
    "state": "posted",
    "invoice_date": "2024-11-05",
    "invoice_date_due": "2024-12-05",
    "amount_total": 48500.00
  }
]
```

**Errors**
- `404` PO not found
- `422` PO is not in `done` status / PO has no `odoo_id`
- `502` No vendor bills found in Odoo

---

## 5. Response Object Schemas

### `PurchaseOrderOut`

| Field | Type | Source |
|---|---|---|
| `id` | int | local DB |
| `odoo_id` | int \| null | Odoo record ID |
| `display_name` | string | webhook / Odoo |
| `package_id` | string \| null | webhook / Odoo |
| `partner_id` | string \| null | webhook / Odoo |
| `project_id` | string \| null | webhook / Odoo |
| `subject` | string \| null | webhook |
| `category` | string \| null | webhook |
| `status` | string | kanban state machine |
| `created_at` | datetime | local DB |
| `updated_at` | datetime | local DB |
| `vendor_name` | string \| null | Odoo `partner_ref` — after sync |
| `po_number` | string \| null | Odoo `package_number` — after sync |
| `confirmation_date` | string \| null | Odoo `first_confirmation_date` — after sync |
| `delivery_date` | string \| null | Odoo `delivery_date` — after sync |
| `placement_date` | string \| null | Odoo `date_approve` — after sync |
| `odoo_synced_at` | datetime \| null | timestamp of last Odoo sync |
| `line_items` | `POLineItemOut[]` | populated after sync |
| `grn_receipts` | `GRNReceiptOut[]` | populated after `/fetch-grn` |
| `prq_receipts` | `PRQReceiptOut[]` | populated after `/fetch-prq` |

---

### `POLineItemOut`

| Field | Type | Source |
|---|---|---|
| `id` | int | local DB |
| `odoo_line_id` | int \| null | Odoo `purchase.order.line` ID |
| `product_name` | string \| null | Odoo `product_id` |
| `qty_ordered` | float \| null | Odoo `product_qty` |
| `qty_received` | float \| null | Odoo `qty_received` — filled after GRN validated |
| `qty_invoiced` | float \| null | Odoo `qty_invoiced` — filled after vendor bill posted |
| `price_unit` | float \| null | Odoo `price_unit` |
| `package_id` | string \| null | Odoo `package_id` |

---

### `GRNReceiptOut`

| Field | Type | Notes |
|---|---|---|
| `id` | int | local DB |
| `odoo_picking_id` | int \| null | Odoo `stock.picking` ID |
| `name` | string \| null | e.g. `WH/IN/00012` |
| `state` | string \| null | `draft` / `confirmed` / `done` / `cancel` |
| `scheduled_date` | string \| null | expected receipt date |
| `date_done` | string \| null | actual validation date — null until `state = done` |

---

### `PRQReceiptOut`

| Field | Type | Notes |
|---|---|---|
| `id` | int | local DB |
| `odoo_invoice_id` | int \| null | Odoo `account.move` ID |
| `name` | string \| null | e.g. `BILL/2024/00012` |
| `state` | string \| null | `draft` / `posted` / `cancel` |
| `invoice_date` | string \| null | bill date |
| `invoice_date_due` | string \| null | payment due date |
| `amount_total` | float \| null | total amount including tax |

---

### `WebhookAck`

| Field | Type | Notes |
|---|---|---|
| `accepted` | bool | always `true` on success |
| `po_id` | int \| null | local DB ID of the upserted PO |
| `created` | bool | `true` = new card, `false` = updated existing |
| `message` | string | human-readable result |
| `extracted` | object | normalised fields parsed from the webhook body |

---

## 6. Kanban Status Flow

```
new  ──►  in_review  ──►  in_progress  ──►  done
                               │
                          fetch-grn             fetch-prq
                         (stock.picking)      (account.move)
```

Status can be set to any value via `PATCH /po/{id}/status` — the flow above is the intended progression but is not enforced server-side.

---

## 7. Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | SQLAlchemy DB URL (SQLite or Postgres) |
| `ODOO_URL` | For sync | Full JSON-RPC endpoint, e.g. `https://company.odoo.com/jsonrpc` |
| `ODOO_DB` | For sync | Odoo database name |
| `ODOO_USER_ID` | For sync | Numeric Odoo user ID (integer, not email) |
| `ODOO_API_KEY` | For sync | API key from Odoo user preferences |
| `WEBHOOK_ALLOWED_IPS` | No | Comma-separated IPs allowed to POST the webhook. Empty = allow all |
| `CORS_ORIGINS` | No | Comma-separated allowed origins. Defaults to `localhost:5173` |
