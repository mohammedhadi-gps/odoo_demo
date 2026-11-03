import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KANBAN_COLUMNS, POLineItem, PurchaseOrder, WebhookLog
from app.odoo_parse import normalize_po_payload

logger = logging.getLogger(__name__)


def list_purchase_orders(db: Session, project_id: str | None = None, status: str | None = None) -> list[PurchaseOrder]:
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.updated_at.desc())
    if project_id:
        stmt = stmt.where(PurchaseOrder.project_id == project_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    return list(db.scalars(stmt))


def get_purchase_order(db: Session, row_id: int) -> PurchaseOrder | None:
    return db.get(PurchaseOrder, row_id)


def upsert_from_webhook(db: Session, payload: dict[str, Any]) -> tuple[PurchaseOrder, bool]:
    fields = normalize_po_payload(payload)
    existing = None
    if fields["odoo_id"] is not None:
        existing = db.scalar(select(PurchaseOrder).where(PurchaseOrder.odoo_id == fields["odoo_id"]))
    if existing is None and fields["display_name"]:
        existing = db.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.display_name == fields["display_name"],
                PurchaseOrder.status != "done",
            )
        )

    created = existing is None
    row = existing or PurchaseOrder(status="new")
    row.odoo_id = fields["odoo_id"] or row.odoo_id
    row.display_name = fields["display_name"]
    row.package_id = fields["package_id"]
    row.partner_id = fields["partner_id"]
    row.project_id = fields["project_id"]
    row.subject = fields["subject"]
    row.category = fields["category"]
    row.raw_payload = json.dumps(payload, default=str)
    if created:
        row.status = "new"
        db.add(row)
    db.commit()
    db.refresh(row)
    return row, created


def update_status(db: Session, row: PurchaseOrder, status: str) -> PurchaseOrder:
    if status not in KANBAN_COLUMNS:
        raise ValueError(f"Invalid status: {status}")
    row.status = status
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_log(db: Session, log_type: str, message: str, payload: str | None) -> None:
    db.add(WebhookLog(log_type=log_type, message=message, payload=payload))
    db.commit()


def apply_odoo_enrichment(db: Session, row: PurchaseOrder, enrichment: dict, lines: list[dict]) -> PurchaseOrder:
    """
    Apply fields fetched from Odoo JSON-RPC onto an existing PurchaseOrder row
    and replace its line items.
    """
    row.vendor_name = enrichment.get("vendor_name") or row.vendor_name
    row.po_number = enrichment.get("po_number") or row.po_number
    row.confirmation_date = enrichment.get("confirmation_date") or row.confirmation_date
    row.delivery_date = enrichment.get("delivery_date") or row.delivery_date
    row.placement_date = enrichment.get("placement_date") or row.placement_date
    row.odoo_synced_at = datetime.now(timezone.utc)

    # Replace all line items
    db.query(POLineItem).filter(POLineItem.purchase_order_id == row.id).delete()
    for line in lines:
        db.add(POLineItem(purchase_order_id=row.id, **line))

    db.add(row)
    db.commit()
    db.refresh(row)
    return row
