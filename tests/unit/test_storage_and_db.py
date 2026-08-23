from sqlalchemy import select, text

from citizens.db.migrate import run_migrations
from citizens.db.models import AuditEvent
from citizens.db.session import configure_database, session_scope, sqlite_url
from citizens.storage.paths import SUBDIRS, db_path, ensure_storage_layout


def test_storage_layout_created(tmp_path):
    root = tmp_path / "storage"
    ensure_storage_layout(root)
    for sub in SUBDIRS:
        assert (root / sub).is_dir()


def test_migrations_and_audit_event(tmp_path):
    root = tmp_path / "storage"
    ensure_storage_layout(root)
    url = sqlite_url(db_path(root))
    configure_database(url)
    run_migrations(url)

    with session_scope() as session:
        session.add(AuditEvent(event="test_event", actor="tester"))
    with session_scope() as session:
        stored = session.execute(select(AuditEvent)).scalar_one()
        assert stored.event == "test_event"
        assert stored.id  # uuid assigned
        assert stored.created_at is not None


def test_sqlite_pragmas(tmp_path):
    root = tmp_path / "storage"
    ensure_storage_layout(root)
    engine = configure_database(sqlite_url(db_path(root)))
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
