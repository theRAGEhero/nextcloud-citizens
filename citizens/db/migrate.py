"""Programmatic Alembic migrations, run at application startup."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations(db_url: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")
