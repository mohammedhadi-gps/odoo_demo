# Odoo PO Kanban

Receives purchase orders from Odoo via webhook and shows them on a kanban board.

Webhook fields stored on each card:

- `display_name`
- `package_id`
- `partner_id`
- `project_id`
- `subject`
- `category`

## Run locally

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

The board polls `/api/v1/po/board` every 5 seconds. Drag a card to change status.

## Odoo webhook (production-style setup)

1. Go to **Settings → Technical → Server Actions**
2. Click **New**
3. Fill in:
   - **Name:** Purchase Order Status locked update
   - **Action Type:** Send Webhook Notification
   - **Model:** `purchase.order`
   - **Webhook URL:** `https://YOUR-HOST/api/v1/odoo/po-webhook`
   - **Fields to Send:** `display_name`, `package_id`, `partner_id`, `project_id`, `subject`, `category`
4. Save

For local testing, use a tunnel (ngrok, Cloudflare Tunnel, etc.) pointing at `http://localhost:8000`.

Optional IP allow-list: set `WEBHOOK_ALLOWED_IPS` in `backend/.env`.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/odoo/po-webhook` | Odoo PO webhook |
| GET | `/api/v1/po/board` | Kanban columns |
| GET | `/api/v1/po/pending` | POs in `new` |
| GET | `/api/v1/po` | All POs |
| PATCH | `/api/v1/po/{id}/status` | Move a card |
| POST | `/api/v1/po/pending/{id}/process` | Mark in progress with `wp_ids` |

Example payload Odoo may send (many2one fields often arrive as `[id, name]`):

```json
{
  "_id": 1842,
  "_model": "purchase.order",
  "display_name": "PO/2026/00412",
  "package_id": [8, "PKG-CIVIL-02"],
  "partner_id": [55, "Acme Vendors"],
  "project_id": [3, "Site Alpha"],
  "subject": "Foundation bolts",
  "category": "Civil"
}
```

Local test:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/odoo/po-webhook \
  -H "Content-Type: application/json" \
  -d '{"_id":1,"display_name":"PO/TEST","package_id":[1,"PKG-1"],"partner_id":[2,"Vendor"],"project_id":[3,"Project A"],"subject":"Cables","category":"Electrical"}'
```

Kanban columns: `new` → `in_review` → `in_progress` → `done`.
