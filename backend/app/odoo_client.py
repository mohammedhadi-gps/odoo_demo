"""
Odoo JSON-RPC client.

Requires these environment variables (set on the server, not in .env):
    ODOO_URL      - full JSON-RPC endpoint, e.g. https://mycompany.odoo.com/jsonrpc
    ODOO_DB       - Odoo database name
    ODOO_USER_ID  - numeric user ID (not the login email)
    ODOO_API_KEY  - API key generated in Odoo user preferences
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Fields fetched from purchase.order
PO_FIELDS = [
    "id",
    "name",
    "partner_ref",              # Vendor Name (vendor's own reference)
    "first_confirmation_date",  # Confirmation Date (custom field)
    "delivery_date",            # Contractual Delivery Date (custom field)
    "package_number",           # PO Number (custom field)
    "date_approve",             # PO Placement Date (standard)
    "partner_id",
    "project_id",
    "package_id",
    "order_line",               # list of purchase.order.line IDs
    "invoice_ids",              # list of account.move IDs (vendor bills / PRQs)
]

# Fields fetched from purchase.order.line
LINE_FIELDS = [
    "id",
    "product_id",
    "product_qty",    # ordered quantity
    "qty_received",   # filled after GRN / stock receipt is validated
    "qty_invoiced",   # filled after vendor bill (PRQ) is posted
    "price_unit",
    "package_id",
]

# Fields fetched from stock.picking (GRN receipts)
GRN_FIELDS = [
    "id",
    "name",             # receipt reference e.g. WH/IN/00012
    "state",            # draft / confirmed / done / cancel
    "scheduled_date",   # expected receipt date
    "date_done",        # actual date validated (filled when state=done)
]

# Fields fetched from account.move (PRQ / vendor bills)
PRQ_FIELDS = [
    "id",
    "name",               # bill reference e.g. BILL/2024/00012
    "state",              # draft / posted / cancel
    "invoice_date",       # bill date
    "invoice_date_due",   # payment due date
    "amount_total",       # total amount including tax
]


def _build_payload(model: str, method: str, args: list, kwargs: dict | None = None) -> dict:
    """Build a standard JSON-RPC 2.0 execute_kw payload."""
    return {
        "jsonrpc": "2.0",
        "method": "call",
        "id": 1,
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                settings.odoo_db,
                settings.odoo_user_id,
                settings.odoo_api_key,
                model,
                method,
                args,
                kwargs or {},
            ],
        },
    }


async def _post(payload: dict) -> Any:
    """Send one JSON-RPC request and return the result, or raise on error."""
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        response = await client.post(settings.odoo_url, json=payload)
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        msg = data["error"].get("data", {}).get("message") or str(data["error"])
        raise RuntimeError(f"Odoo JSON-RPC error: {msg}")

    return data.get("result")


async def fetch_latest_purchase_orders(limit: int = 3) -> list[dict]:
    """
    Fetch the most recent confirmed purchase orders from Odoo.
    Filters: state in [purchase, done] (confirmed only, no drafts).
    Ordered by date_approve descending (most recent first).
    """
    if not settings.odoo_configured:
        logger.warning("Odoo connection not configured — skipping bulk PO fetch")
        return []

    payload = _build_payload(
        model="purchase.order",
        method="search_read",
        args=[[["state", "in", ["purchase", "done"]]]],
        kwargs={"fields": PO_FIELDS, "limit": limit, "order": "date_approve desc"},
    )
    try:
        result = await _post(payload)
        logger.info("Fetched %d POs from Odoo", len(result or []))
        return result or []
    except Exception:
        logger.exception("Failed to fetch latest POs from Odoo")
        return []


async def fetch_purchase_order(odoo_id: int) -> dict | None:
    """
    Fetch a single purchase.order by its Odoo numeric ID.
    Returns the record dict or None if not found / Odoo unreachable.
    """
    if not settings.odoo_configured:
        logger.warning("Odoo connection not configured — skipping fetch for PO %s", odoo_id)
        return None

    payload = _build_payload(
        model="purchase.order",
        method="search_read",
        args=[[["id", "=", odoo_id]]],
        kwargs={"fields": PO_FIELDS, "limit": 1},
    )
    try:
        result = await _post(payload)
        return result[0] if result else None
    except Exception:
        logger.exception("Failed to fetch PO %s from Odoo", odoo_id)
        return None


async def fetch_order_lines(line_ids: list[int]) -> list[dict]:
    """
    Fetch purchase.order.line records by their IDs.
    qty_received and qty_invoiced are 0.0 until a GRN or vendor bill is validated.
    """
    if not settings.odoo_configured or not line_ids:
        return []

    payload = _build_payload(
        model="purchase.order.line",
        method="search_read",
        args=[[["id", "in", line_ids]]],
        kwargs={"fields": LINE_FIELDS},
    )
    try:
        result = await _post(payload)
        return result or []
    except Exception:
        logger.exception("Failed to fetch order lines %s from Odoo", line_ids)
        return []


async def fetch_grn_for_po(odoo_po_id: int) -> list[dict]:
    """
    Fetch all incoming stock receipts (GRNs) for a purchase.order.
    Queries stock.picking filtered by purchase_id and picking_type_code=incoming.
    Returns an empty list if none found or Odoo is not configured.
    """
    if not settings.odoo_configured:
        logger.warning("Odoo connection not configured — skipping GRN fetch for PO %s", odoo_po_id)
        return []

    payload = _build_payload(
        model="stock.picking",
        method="search_read",
        args=[[
            ["purchase_id", "=", odoo_po_id],
            ["picking_type_code", "=", "incoming"],
        ]],
        kwargs={"fields": GRN_FIELDS},
    )
    try:
        result = await _post(payload)
        logger.info("Fetched %d GRN(s) for Odoo PO id=%s", len(result or []), odoo_po_id)
        return result or []
    except Exception:
        logger.exception("Failed to fetch GRNs for Odoo PO id=%s", odoo_po_id)
        return []


async def fetch_prq_for_po(invoice_ids: list[int]) -> list[dict]:
    """
    Fetch vendor bills (PRQs) for a purchase.order using the invoice_ids
    already present on the PO record — no broad domain search needed.

    Call pattern:
        po_data = await fetch_purchase_order(odoo_id)
        invoice_ids = po_data.get("invoice_ids") or []
        bills = await fetch_prq_for_po(invoice_ids)

    Uses execute_kw / read (not search_read) so only those exact records
    are returned regardless of how many bills exist in the database.
    """
    if not settings.odoo_configured:
        logger.warning("Odoo connection not configured — skipping PRQ fetch")
        return []
    if not invoice_ids:
        logger.info("No invoice_ids on PO — skipping PRQ fetch")
        return []

    payload = _build_payload(
        model="account.move",
        method="read",
        args=[invoice_ids],
        kwargs={"fields": PRQ_FIELDS},
    )
    try:
        result = await _post(payload)
        logger.info("Fetched %d PRQ(s) for invoice_ids=%s", len(result or []), invoice_ids)
        return result or []
    except Exception:
        logger.exception("Failed to fetch PRQs for invoice_ids=%s", invoice_ids)
        return []


# ── Parsers ──────────────────────────────────────────────────────────────────

def _as_text(value: Any) -> str | None:
    """Coerce an Odoo many2one tuple [id, name] or plain value to a string."""
    if value is None or value is False:
        return None
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and value[1] not in (None, False):
            return str(value[1])
        return str(value[0]) if value else None
    return str(value)


def _as_float(value: Any) -> float | None:
    if value is None or value is False:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_po_enrichment(po: dict) -> dict:
    """Extract enrichment fields from a raw Odoo PO dict for storage."""
    return {
        "vendor_name": _as_text(po.get("partner_ref")) or _as_text(po.get("partner_id")),
        "po_number": _as_text(po.get("package_number")) or _as_text(po.get("name")),
        "confirmation_date": _as_text(po.get("first_confirmation_date")),
        "delivery_date": _as_text(po.get("delivery_date")),
        "placement_date": _as_text(po.get("date_approve")),
    }


def parse_line_items(lines: list[dict]) -> list[dict]:
    """Convert raw Odoo order line dicts to POLineItem shape."""
    return [{
        "odoo_line_id": line.get("id"),
        "product_name": _as_text(line.get("product_id")),
        "qty_ordered": _as_float(line.get("product_qty")),
        "qty_received": _as_float(line.get("qty_received")),
        "qty_invoiced": _as_float(line.get("qty_invoiced")),
        "price_unit": _as_float(line.get("price_unit")),
        "package_id": _as_text(line.get("package_id")),
    } for line in lines]
