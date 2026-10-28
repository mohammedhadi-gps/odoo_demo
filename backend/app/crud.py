import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KANBAN_COLUMNS, PurchaseOrder, WebhookLog
from app.odoo_parse import normalize_po_payload


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
