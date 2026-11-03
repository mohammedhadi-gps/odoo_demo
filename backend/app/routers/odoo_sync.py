"""
Odoo sync endpoints.

POST /api/v1/po/{id}/sync   - Manual sync for a single PO by local DB id
POST /api/v1/odoo/pull      - Pull latest confirmed POs from Odoo into the kanban
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import apply_odoo_enrichment, get_purchase_order, upsert_from_webhook
from app.database import get_db
from app.events import publish
from app.odoo_client import (
    fetch_latest_purchase_orders,
    fetch_order_lines,
    fetch_purchase_order,
    parse_line_items,
    parse_po_enrichment,
)
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


@router.post("/odoo/pull")
async def pull_from_odoo(
    limit: int = Query(default=50, ge=1, le=200, description="Max number of POs to pull"),
    db: Session = Depends(get_db),
):
    """
    Pull the latest confirmed purchase orders from Odoo via JSON-RPC.
    Each PO is upserted into the local DB (created if new, updated if existing).
    Line items are fetched and stored for each PO.
    Returns a summary of what was created vs updated.
    """
    po_list = await fetch_latest_purchase_orders(limit=limit)

    if not po_list:
        raise HTTPException(
            status_code=502,
            detail="No POs returned from Odoo. Check ODOO_* environment variables and Odoo connectivity.",
        )

    created_count = 0
    updated_count = 0
    failed_ids = []

    for po_data in po_list:
        try:
            # Build a webhook-compatible payload so we can reuse upsert_from_webhook
            payload = {
                "id": po_data.get("id"),
                "display_name": po_data.get("name") or f"PO #{po_data.get('id')}",
                "partner_id": po_data.get("partner_id"),
                "project_id": po_data.get("project_id"),
                "package_id": po_data.get("package_id"),
            }
            row, created = upsert_from_webhook(db, payload)

            # Enrich with full Odoo fields + line items
            enrichment = parse_po_enrichment(po_data)
            line_ids = po_data.get("order_line") or []
            lines_raw = await fetch_order_lines(line_ids)
            lines = parse_line_items(lines_raw)
            apply_odoo_enrichment(db, row, enrichment, lines)

            publish({
                "type": "po",
                "po_id": row.id,
                "created": created,
                "status": row.status,
                "display_name": row.display_name,
                "extracted": {},
            })

            if created:
                created_count += 1
            else:
                updated_count += 1

        except Exception:
            logger.exception("Failed to upsert PO odoo_id=%s during pull", po_data.get("id"))
            failed_ids.append(po_data.get("id"))

    logger.info(
        "Odoo pull complete: %d created, %d updated, %d failed",
        created_count, updated_count, len(failed_ids),
    )
    return {
        "status": "ok",
        "created": created_count,
        "updated": updated_count,
        "failed": failed_ids,
        "total": len(po_list),
    }
