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
    "partner_ref",           # Vendor Name
    "first_confirmation_date",  # Confirmation Date (custom)
    "delivery_date",         # Contractual Delivery Date (custom)
    "package_number",        # PO Number (custom)
    "date_approve",          # PO Placement Date
    "partner_id",
    "project_id",
    "package_id",
    "order_line",
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


def _build_payload(model: str, method: str, args: list, kwargs: dict | None = None) -> dict:
    """Build a JSON-RPC 2.0 execute_kw payload."""
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


async def fetch_purchase_order(odoo_id: int) -> dict | None:
    """
    Fetch a single purchase.order by its Odoo ID.
    Returns the first matching record dict, or None.
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
        if result:
            return result[0]
        logger.warning("Odoo returned no PO for id=%s", odoo_id)
        return None
    except Exception:
        logger.exception("Failed to fetch PO %s from Odoo", odoo_id)
        return None


async def fetch_order_lines(line_ids: list[int]) -> list[dict]:
    """
    Fetch purchase.order.line records by their IDs.
    Returns an empty list when nothing is found or Odoo is not configured.

    Note: qty_received and qty_invoiced are computed fields populated only
    after a stock receipt (GRN) or vendor bill (PRQ) is validated in Odoo.
    Before that they will be 0.0.
    """
    if not settings.odoo_configured:
        logger.warning("Odoo connection not configured — skipping order line fetch")
        return []
    if not line_ids:
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
    """
    Extract the enrichment fields we care about from a raw Odoo PO dict.
    Returns a flat dict ready to be applied to a PurchaseOrder row.
    """
    return {
        "vendor_name": _as_text(po.get("partner_ref")) or _as_text(po.get("partner_id")),
        "po_number": _as_text(po.get("package_number")) or _as_text(po.get("name")),
        "confirmation_date": _as_text(po.get("first_confirmation_date")),
        "delivery_date": _as_text(po.get("delivery_date")),
        "placement_date": _as_text(po.get("date_approve")),
    }


def parse_line_items(lines: list[dict]) -> list[dict]:
    """
    Convert raw Odoo order line dicts to the shape expected by POLineItem.
    """
    result = []
    for line in lines:
        result.append({
            "odoo_line_id": line.get("id"),
            "product_name": _as_text(line.get("product_id")),
            "qty_ordered": _as_float(line.get("product_qty")),
            "qty_received": _as_float(line.get("qty_received")),
            "qty_invoiced": _as_float(line.get("qty_invoiced")),
            "price_unit": _as_float(line.get("price_unit")),
            "package_id": _as_text(line.get("package_id")),
        })
    return result
