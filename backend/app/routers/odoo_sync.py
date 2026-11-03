"""
Manual Odoo sync endpoint.

POST /api/v1/po/{id}/sync
  - Fetches the PO and its order lines from Odoo via JSON-RPC
  - Stores enriched fields (vendor_name, po_number, dates) on the PO row
  - Replaces line items with fresh data from Odoo
  - Returns the updated PurchaseOrderOut (including line_items)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import apply_odoo_enrichment, get_purchase_order
from app.database import get_db
from app.events import publish
from app.odoo_client import fetch_order_lines, fetch_purchase_order, parse_line_items, parse_po_enrichment
from app.schemas import PurchaseOrderOut

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/po/{row_id}/sync", response_model=PurchaseOrderOut)
async def sync_po_from_odoo(row_id: int, db: Session = Depends(get_db)):
    """
    Manually trigger an Odoo JSON-RPC sync for a single PO.
    The PO must exist locally and have an odoo_id set.
    """
    row = get_purchase_order(db, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="PO not found")
    if not row.odoo_id:
        raise HTTPException(
            status_code=422,
            detail="This PO has no Odoo ID — cannot sync. Ensure the webhook payload includes '_id' or 'id'.",
        )

    po_data = await fetch_purchase_order(row.odoo_id)
    if not po_data:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch PO {row.odoo_id} from Odoo. Check ODOO_* env vars and connectivity.",
        )

    enrichment = parse_po_enrichment(po_data)
    line_ids = po_data.get("order_line") or []
    lines_raw = await fetch_order_lines(line_ids)
    lines = parse_line_items(lines_raw)

    updated = apply_odoo_enrichment(db, row, enrichment, lines)

    publish({"type": "po_enriched", "po_id": row_id})
    logger.info("Manual sync completed for PO %s (odoo_id=%s)", row_id, row.odoo_id)

    return PurchaseOrderOut.model_validate(updated)
