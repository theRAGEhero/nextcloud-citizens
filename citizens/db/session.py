"""Database engine/session management.

SQLite in APP_PERSISTENT_STORAGE with WAL mode and enforced foreign keys.
Kept behind small functions so PostgreSQL could be supported later without
touching callers.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


def configure_database(db_url: str) -> Engine:
    global _engine, _session_factory
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    _engine = create_engine(db_url, connect_args=connect_args)
    if db_url.startswith("sqlite"):
        event.listen(_engine, "connect", _set_sqlite_pragmas)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database is not configured; call configure_database() first")
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    if _session_factory is None:
        raise RuntimeError("Database is not configured; call configure_database() first")
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session
