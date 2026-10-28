import json
from typing import Any

RECORD_KEYS = {
    "_id",
    "id",
    "display_name",
    "name",
    "package_id",
    "partner_id",
    "project_id",
    "subject",
    "category",
}


def _as_text(value: Any) -> str | None:
    if value is None or value is False:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        if len(value) >= 2 and value[1] not in (None, False):
            return str(value[1])
        return str(value[0])
    if isinstance(value, dict):
        for key in ("display_name", "name", "complete_name"):
            if value.get(key) not in (None, False):
                return str(value[key])
        if value.get("id") not in (None, False):
            return str(value["id"])
        return None
    return str(value)


def extract_odoo_id(payload: dict[str, Any]) -> int | None:
    for key in ("_id", "id", "res_id"):
        raw = payload.get(key)
        if isinstance(raw, bool) or raw in (None, False):
            continue
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
        if isinstance(raw, (list, tuple)) and raw:
            first = raw[0]
            if isinstance(first, int):
                return first
            if isinstance(first, str) and first.isdigit():
                return int(first)
        if isinstance(raw, dict) and raw.get("id") is not None:
            try:
                return int(raw["id"])
            except (TypeError, ValueError):
                continue
    return None


def extract_records(body: Any) -> list[dict[str, Any]]:
    if body in (None, False, "", b"", bytearray()):
        return []
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8", errors="replace")
    if isinstance(body, str):
        text = body.strip()
        if not text:
            return []
        try:
            return extract_records(json.loads(text))
        except json.JSONDecodeError:
            return [{"display_name": text}]
    if isinstance(body, list):
        records: list[dict[str, Any]] = []
        for item in body:
            records.extend(extract_records(item))
        return records
    if not isinstance(body, dict):
        return []

    envelope = {key: body[key] for key in ("_id", "_model", "id") if key in body}
    for key in ("params", "data", "record", "records", "payload", "values", "result"):
        nested = body.get(key)
        if nested in (None, False, ""):
            continue
        extracted = extract_records(nested)
        if extracted:
            return [{**envelope, **record} for record in extracted]

    return [body]


def normalize_po_payload(payload: dict[str, Any]) -> dict[str, Any]:
    odoo_id = extract_odoo_id(payload)
    display_name = (
        _as_text(payload.get("display_name"))
        or _as_text(payload.get("name"))
        or (f"PO #{odoo_id}" if odoo_id is not None else "Purchase order")
    )
    return {
        "odoo_id": odoo_id,
        "display_name": display_name,
        "package_id": _as_text(payload.get("package_id")),
        "partner_id": _as_text(payload.get("partner_id")),
        "project_id": _as_text(payload.get("project_id")),
        "subject": _as_text(payload.get("subject")),
        "category": _as_text(payload.get("category")),
    }
