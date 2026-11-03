import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.crud import create_log, upsert_from_webhook
from app.database import get_db
from app.events import publish
from app.odoo_parse import extract_records, normalize_po_payload
from app.schemas import WebhookAck
from app.security import verify_client_ip

logger = logging.getLogger(__name__)
router = APIRouter()


async def _read_body(request: Request):
    raw = await request.body()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Odoo webhook body was not JSON, storing raw text")
        return {"display_name": raw.decode("utf-8", errors="replace")}


def _enrich_in_background(po_id: int, odoo_id: int | None) -> None:
    """
    Kick off an Odoo JSON-RPC enrichment for a PO in a background thread.
    Runs synchronously inside FastAPI's thread pool via run_in_threadpool.
    """
    if odoo_id is None:
        return
    import asyncio

    from app.crud import apply_odoo_enrichment, get_purchase_order
    from app.database import SessionLocal
    from app.odoo_client import fetch_order_lines, fetch_purchase_order, parse_line_items, parse_po_enrichment

    async def _run():
        po_data = await fetch_purchase_order(odoo_id)
        if not po_data:
            return
        enrichment = parse_po_enrichment(po_data)
        line_ids = po_data.get("order_line") or []
        lines_raw = await fetch_order_lines(line_ids)
        lines = parse_line_items(lines_raw)

        db = SessionLocal()
        try:
            row = get_purchase_order(db, po_id)
            if row:
                apply_odoo_enrichment(db, row, enrichment, lines)
                publish({"type": "po_enriched", "po_id": po_id})
                logger.info("Enriched PO %s from Odoo (odoo_id=%s)", po_id, odoo_id)
        finally:
            db.close()

    asyncio.run(_run())


@router.post("/odoo/po-webhook", response_model=WebhookAck)
async def po_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    client_ip: str = Depends(verify_client_ip),
):
    payload = {}
    try:
        payload = await _read_body(request)
        logger.info("Received PO payload from %s: %s", client_ip, payload)

        records = extract_records(payload) or [payload if isinstance(payload, dict) else {}]
        saved = []
        for record in records:
            if not isinstance(record, dict):
                record = {"display_name": str(record)}
            row, created = upsert_from_webhook(db, record)
            extracted = normalize_po_payload(record)
            publish(
                {
                    "type": "po",
                    "po_id": row.id,
                    "created": created,
                    "status": row.status,
                    "display_name": row.display_name,
                    "extracted": extracted,
                }
            )
            saved.append((row, created, extracted))
            # Schedule Odoo enrichment as a background task
            background_tasks.add_task(_enrich_in_background, row.id, row.odoo_id)

        row, created, extracted = saved[0]
        result = WebhookAck(
            accepted=True,
            po_id=row.id,
            created=created,
            message="PO created on kanban" if created else "PO updated on kanban",
            extracted=extracted,
        )
        create_log(db, "po", str(result.model_dump()), json.dumps(payload, default=str))
        return result
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("PO webhook processing failed")
        create_log(
            db,
            "po",
            f"Failed: {error}",
            json.dumps(payload, default=str) if payload else None,
        )
        raise HTTPException(status_code=500, detail=str(error)) from error
