from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

KANBAN_COLUMNS = ("new", "in_review", "in_progress", "done")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("odoo_id", name="uq_purchase_orders_odoo_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    odoo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    package_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    partner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="new", index=True)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fields enriched via Odoo JSON-RPC
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)       # partner_ref
    po_number: Mapped[str | None] = mapped_column(String(255), nullable=True)         # package_number
    confirmation_date: Mapped[str | None] = mapped_column(String(50), nullable=True)  # first_confirmation_date
    delivery_date: Mapped[str | None] = mapped_column(String(50), nullable=True)      # delivery_date
    placement_date: Mapped[str | None] = mapped_column(String(50), nullable=True)     # date_approve
    odoo_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    line_items: Mapped[list["POLineItem"]] = relationship(
        "POLineItem", back_populates="purchase_order", cascade="all, delete-orphan"
    )
    grn_receipts: Mapped[list["GRNReceipt"]] = relationship(
        "GRNReceipt", back_populates="purchase_order", cascade="all, delete-orphan"
    )


class POLineItem(Base):
    __tablename__ = "po_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    purchase_order_id: Mapped[int] = mapped_column(Integer, ForeignKey("purchase_orders.id"), index=True)
    odoo_line_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    qty_ordered: Mapped[float | None] = mapped_column(Float, nullable=True)
    qty_received: Mapped[float | None] = mapped_column(Float, nullable=True)   # from GRN
    qty_invoiced: Mapped[float | None] = mapped_column(Float, nullable=True)   # from PRQ/bill
    price_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    package_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="line_items")


class GRNReceipt(Base):
    __tablename__ = "grn_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    purchase_order_id: Mapped[int] = mapped_column(Integer, ForeignKey("purchase_orders.id"), index=True)
    odoo_picking_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)   # e.g. WH/IN/00012
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)   # draft/confirmed/done/cancel
    scheduled_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date_done: Mapped[str | None] = mapped_column(String(50), nullable=True)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="grn_receipts")


class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_type: Mapped[str] = mapped_column(String(50), default="po")
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
