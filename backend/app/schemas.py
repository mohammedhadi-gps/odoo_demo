from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

KanbanStatus = Literal["new", "in_review", "in_progress", "done"]


class GRNReceiptOut(BaseModel):
    id: int
    odoo_picking_id: int | None
    name: str | None
    state: str | None
    scheduled_date: str | None
    date_done: str | None

    model_config = {"from_attributes": True}


class POLineItemOut(BaseModel):
    id: int
    odoo_line_id: int | None
    product_name: str | None
    qty_ordered: float | None
    qty_received: float | None
    qty_invoiced: float | None
    price_unit: float | None
    package_id: str | None

    model_config = {"from_attributes": True}


class PurchaseOrderOut(BaseModel):
    id: int
    odoo_id: int | None
    display_name: str
    package_id: str | None
    partner_id: str | None
    project_id: str | None
    subject: str | None
    category: str | None
    status: str
    created_at: datetime | None
    updated_at: datetime | None

    # Enriched via Odoo JSON-RPC
    vendor_name: str | None = None
    po_number: str | None = None
    confirmation_date: str | None = None
    delivery_date: str | None = None
    placement_date: str | None = None
    odoo_synced_at: datetime | None = None
    line_items: list[POLineItemOut] = Field(default_factory=list)
    grn_receipts: list[GRNReceiptOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class StatusUpdate(BaseModel):
    status: KanbanStatus


class ProcessPayload(BaseModel):
    wp_ids: list[str] = Field(default_factory=list)


class KanbanBoard(BaseModel):
    columns: dict[str, list[PurchaseOrderOut]]


class WebhookAck(BaseModel):
    accepted: bool
    po_id: int | None = None
    created: bool = False
    message: str
    extracted: dict[str, Any] = Field(default_factory=dict)
