from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

KanbanStatus = Literal["new", "in_review", "in_progress", "done"]


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
