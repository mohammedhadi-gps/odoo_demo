import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import get_purchase_order, list_purchase_orders, update_status
from app.database import get_db
from app.models import KANBAN_COLUMNS
from app.schemas import KanbanBoard, ProcessPayload, PurchaseOrderOut, StatusUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/po/pending", response_model=list[PurchaseOrderOut])
def list_pending(
    db: Session = Depends(get_db),
    project_id: str | None = Query(default=None),
):
    return list_purchase_orders(db, project_id=project_id, status="new")


@router.get("/po", response_model=list[PurchaseOrderOut])
def list_all_pos(
    db: Session = Depends(get_db),
    project_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    return list_purchase_orders(db, project_id=project_id, status=status)


@router.get("/po/board", response_model=KanbanBoard)
def get_board(
    db: Session = Depends(get_db),
    project_id: str | None = Query(default=None),
):
    rows = list_purchase_orders(db, project_id=project_id)
    columns = {column: [] for column in KANBAN_COLUMNS}
    for row in rows:
        columns.setdefault(row.status, []).append(PurchaseOrderOut.model_validate(row))
    return KanbanBoard(columns=columns)


@router.patch("/po/{row_id}/status", response_model=PurchaseOrderOut)
def move_po(
    row_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
):
    row = get_purchase_order(db, row_id)
    if not row:
        raise HTTPException(404, "PO not found")
    try:
        return update_status(db, row, body.status)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/po/pending/{row_id}/process")
def process_pending_po(
    row_id: int,
    body: ProcessPayload,
    db: Session = Depends(get_db),
):
    row = get_purchase_order(db, row_id)
    if not row:
        raise HTTPException(404, "Pending PO not found")
    if row.status == "in_progress":
        raise HTTPException(status_code=409, detail="PO mapping already in progress")
    if row.status == "done":
        raise HTTPException(status_code=400, detail="PO already processed")
    if not body.wp_ids:
        raise HTTPException(400, "No work packages selected")

    update_status(db, row, "in_progress")
    logger.info("PO %s assigned work packages %s", row_id, body.wp_ids)
    return {
        "accepted": True,
        "row_id": row_id,
        "status": "in_progress",
        "wp_ids": body.wp_ids,
    }
