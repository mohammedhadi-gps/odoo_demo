# Odoo PO Kanban — API Documentation

A kanban board that tracks Odoo Purchase Orders across four stages.
Backend: FastAPI + PostgreSQL (Supabase). Frontend: React + Vite. Hosted on Vercel.

---

## Architecture

```
Odoo ──webhook──► Backend API ──SSE──► Frontend (Kanban board)
  ▲                   │
  └──── JSON-RPC ─────┘
```

- **Webhook (Odoo → App):** Odoo pushes a notification when a PO is confirmed.
- **JSON-RPC (App → Odoo):** App calls Odoo to fetch full PO data, line items, and GRNs.
- **SSE (App → Browser):** Backend streams live events to the frontend so cards appear instantly.

---

## Environment Variables

Set these in Vercel (Settings → Environment Variables):

| Variable | Description |
|---|---|
| `DATABASE_URL` | Supabase PostgreSQL connection string (Transaction Pooler URL) |
| `ODOO_URL` | Odoo JSON-RPC endpoint — `https://your-odoo.com/jsonrpc` |
| `ODOO_DB` | Odoo database name |
| `ODOO_USER_ID` | Numeric Odoo user ID (found in the URL when viewing a user in Odoo) |
| `ODOO_API_KEY` | API key from Odoo user preferences |
| `CORS_ORIGINS` | Comma-separated allowed origins (e.g. your Vercel frontend URL) |
| `WEBHOOK_ALLOWED_IPS` | Optional comma-separated IP allowlist for the webhook endpoint |

---

## Kanban Columns

| Column | Status value | Purpose |
|---|---|---|
| New | `new` | PO just arrived via webhook or pull |
| In review | `in_review` | Vendor and package being checked |
| In progress (GRN) | `in_progress` | GRN fetch available here |
| Done | `done` | Fully processed |

---

## REST API Endpoints

All endpoints are prefixed with `/api/v1`.

---

### Kanban Board

#### `GET /po/board`
Returns all POs grouped by kanban column.

**Query params:** `project_id` (optional filter)

**Response:**
```json
{
  "columns": {
    "new": [ { ...PurchaseOrderOut } ],
    "in_review": [],
    "in_progress": [],
    "done": []
  }
}
```

---

#### `GET /po`
Returns a flat list of all POs.

**Query params:** `project_id`, `status` (both optional)

---

#### `GET /po/pending`
Returns only POs with status `new`.

---

#### `PATCH /po/{id}/status`
Move a PO to a different kanban column.

**Body:**
```json
{ "status": "in_review" }
```
Valid values: `new`, `in_review`, `in_progress`, `done`

---

#### `DELETE /po/{id}`
Permanently delete a PO and all its line items and GRN records from the local database.
Does not affect Odoo. Returns `204 No Content`.

---

### Webhook (Odoo → App)

#### `POST /odoo/po-webhook`
Receives a PO payload from Odoo when a purchase order is confirmed/locked.

**What it does:**
1. Parses the payload (handles single records, arrays, nested envelopes)
2. Upserts the PO into the local database (create or update by `odoo_id`)
3. Publishes an SSE event so the card appears on the board immediately
4. Fires a background JSON-RPC call back to Odoo to fetch full enrichment + line items

**Response:**
```json
{
  "accepted": true,
  "po_id": 42,
  "created": true,
  "message": "PO created on kanban",
  "extracted": { "odoo_id": 123, "display_name": "PO/00042", ... }
}
```

**Configure in Odoo:** Settings → Technical → Automation → Webhooks
Set the URL to `https://your-app.vercel.app/api/v1/odoo/po-webhook`

---

### Odoo Sync (App → Odoo via JSON-RPC)

#### `POST /odoo/pull?limit=3`
Manually pull the latest confirmed POs from Odoo into the kanban.

**What it does:**
- Calls `purchase.order` `search_read` filtered by `state in [purchase, done]`
- Orders by `date_approve desc` (most recent first)
- Upserts each PO and fetches full enrichment + line items
- Default limit: 3. Max: 200.

**Response:**
```json
{ "status": "ok", "created": 2, "updated": 1, "failed": [], "total": 3 }
```

---

#### `POST /po/{id}/sync`
Manually re-sync a single PO from Odoo. Fetches updated fields and line items.

Requires the PO to have an `odoo_id` (set when created via webhook or pull).

**Response:** Full `PurchaseOrderOut` with updated enrichment and line items.

---

#### `POST /po/{id}/fetch-grn`
Fetch GRN (Goods Receipt Notes) from Odoo for a PO.

Only available when the PO is in `in_progress` status.
Queries `stock.picking` filtered by `purchase_id` and `picking_type_code=incoming`.
Replaces any previously stored GRN records for this PO.

**Response:**
```json
[
  {
    "id": 1,
    "odoo_picking_id": 55,
    "name": "WH/IN/00012",
    "state": "done",
    "scheduled_date": "2026-10-01",
    "date_done": "2026-10-03"
  }
]
```

---

### Live Events (SSE)

#### `GET /po/events`
Server-Sent Events stream. The frontend subscribes to this to receive real-time updates.

**Event types:**

| type | Fired when |
|---|---|
| `po` | A PO is created or updated (via webhook or pull) |
| `po_enriched` | Background JSON-RPC enrichment completed for a PO |
| `po_grn_fetched` | GRN records fetched and stored for a PO |

---

### Health

#### `GET /health`
Returns `{ "status": "ok" }`. Used to verify the backend is running.

---

## Odoo JSON-RPC Calls (Internal)

These are made by the backend to Odoo. Not public endpoints.

| Function | Odoo Model | Purpose |
|---|---|---|
| `fetch_latest_purchase_orders` | `purchase.order` | Pull N most recent confirmed POs |
| `fetch_purchase_order` | `purchase.order` | Fetch one PO by its Odoo ID |
| `fetch_order_lines` | `purchase.order.line` | Fetch line items for a PO |
| `fetch_grn_for_po` | `stock.picking` | Fetch GRN receipts linked to a PO |

### Fields fetched per model

**`purchase.order`**
`id`, `name`, `partner_ref`, `first_confirmation_date`, `delivery_date`,
`package_number`, `date_approve`, `partner_id`, `project_id`, `package_id`, `order_line`

**`purchase.order.line`**
`id`, `product_id`, `product_qty`, `qty_received`, `qty_invoiced`, `price_unit`, `package_id`

> `qty_received` and `qty_invoiced` are Odoo computed fields.
> They show `0.0` until a stock receipt (GRN) or vendor bill is validated in Odoo.

**`stock.picking`** (GRN)
`id`, `name`, `state`, `scheduled_date`, `date_done`

---

## Database Tables

| Table | Purpose |
|---|---|
| `purchase_orders` | Core PO data + enriched fields from Odoo |
| `po_line_items` | Product lines per PO (from `purchase.order.line`) |
| `grn_receipts` | GRN receipts per PO (from `stock.picking`) |
| `webhook_logs` | Raw log of every webhook received |

Tables are created automatically on first startup via SQLAlchemy `create_all`.

---

## Frontend API calls (`frontend/src/api.js`)

| Function | Method | Endpoint | Purpose |
|---|---|---|---|
| `fetchBoard(projectId)` | GET | `/po/board` | Load all columns |
| `movePo(id, status)` | PATCH | `/po/{id}/status` | Drag card to new column |
| `deletePo(id)` | DELETE | `/po/{id}` | Remove card from board |
| `syncPo(id)` | POST | `/po/{id}/sync` | Re-sync one PO from Odoo |
| `pullFromOdoo(limit)` | POST | `/odoo/pull` | Pull latest 3 POs from Odoo |
| `fetchGrn(id)` | POST | `/po/{id}/fetch-grn` | Fetch GRN for in-progress PO |
| `sendTestWebhook(payload)` | POST | `/odoo/po-webhook` | Simulate an Odoo webhook |
| `subscribeBoard(onEvent)` | SSE | `/po/events` | Subscribe to live updates |
