from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def _normalize_url(url: str) -> str:
    """
    Normalize a Postgres/Supabase/Neon connection URL for SQLAlchemy + psycopg v3.

    - postgres://...     -> postgresql+psycopg://...
    - postgresql://...   -> postgresql+psycopg://...
    - sqlite://...       -> unchanged

    Also strips Supabase UI-only query params that psycopg rejects (e.g. supa=base-pooler.x).
    """
    from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

    # Rewrite scheme for psycopg v3
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]

    # Strip query params that are not valid psycopg connection options.
    # Valid ones we keep: sslmode, connect_timeout, application_name, options.
    _VALID_PG_PARAMS = {"sslmode", "connect_timeout", "application_name", "options"}
    parsed = urlparse(url)
    if parsed.query:
        filtered = {
            k: v for k, v in parse_qs(parsed.query, keep_blank_values=True).items()
            if k in _VALID_PG_PARAMS
        }
        clean_query = urlencode({k: v[0] for k, v in filtered.items()})
        url = urlunparse(parsed._replace(query=clean_query))

    return url


database_url = _normalize_url(settings.database_url)
is_sqlite = database_url.startswith("sqlite")

if is_sqlite:
    connect_args = {"check_same_thread": False}
    engine = create_engine(database_url, connect_args=connect_args)
else:
    # Serverless-safe Postgres settings:
    # - pool_size=1, max_overflow=0  → never hold more than 1 connection
    #   (Vercel functions are short-lived; large pools waste Supabase connections)
    # - pool_pre_ping=True           → drop stale connections between invocations
    # SSL is handled by the connection string itself (sslmode=require in the URL)
    engine = create_engine(
        database_url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
