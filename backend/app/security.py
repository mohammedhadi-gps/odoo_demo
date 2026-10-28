from fastapi import HTTPException, Request

from app.config import settings


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def verify_client_ip(request: Request) -> str:
    ip = client_ip(request)
    allowed = settings.allowed_ip_list
    if allowed and ip not in allowed:
        raise HTTPException(status_code=403, detail="Webhook IP is not allowed")
    return ip
