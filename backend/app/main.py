import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app import models as _models  # noqa: F401 — registers all ORM models with Base.metadata
from app.routers import odoo_sync, po_assign, webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables — wrapped so a bad DATABASE_URL gives a readable log instead of
# a cryptic 500 on the first request.
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created.")
except Exception as _db_err:
    logger.error(
        "Could not connect to the database on startup: %s\n"
        "Check that DATABASE_URL is set correctly in Vercel environment variables "
        "and that the Supabase Transaction Pooler URL (port 6543) is used.",
        _db_err,
    )

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(webhook.router)
api_router.include_router(po_assign.router)
api_router.include_router(odoo_sync.router)
app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
