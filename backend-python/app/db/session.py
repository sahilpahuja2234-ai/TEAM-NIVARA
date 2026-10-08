"""SQLite engine, WAL mode, and the get_db dependency."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def _ensure_sqlite_dir(url: str) -> None:
    """Create the parent directory of a file-based SQLite DB (e.g. data/)."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(settings.database_url)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=settings.sql_echo,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Applied to every new connection.

    journal_mode=WAL is persisted in the DB file, but foreign_keys and
    busy_timeout are per-connection in SQLite, so they must be set here
    rather than once at startup.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def init_db() -> None:
    """Create all tables. Importing models registers them on SQLModel.metadata."""
    from app.db import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
