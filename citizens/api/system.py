"""Health/system endpoints."""

import shutil
import uuid

from fastapi import APIRouter
from sqlalchemy import text

from citizens.config import get_settings
from citizens.db.session import get_engine
from citizens.storage.paths import temp_dir

router = APIRouter()


@router.get("/health")
def health() -> dict:
    settings = get_settings()

    db_ok = False
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    storage_ok = False
    try:
        probe = temp_dir(settings.app_persistent_storage) / f".health-{uuid.uuid4().hex}"
        probe.write_text("ok")
        probe.unlink()
        storage_ok = True
    except OSError:
        pass

    try:
        usage = shutil.disk_usage(settings.app_persistent_storage)
        disk_free_gb = round(usage.free / 1024**3, 1)
    except OSError:
        disk_free_gb = None

    return {
        "app": settings.app_id,
        "version": settings.app_version,
        "status": "ok" if (db_ok and storage_ok) else "degraded",
        "database": "ok" if db_ok else "error",
        "storage": "ok" if storage_ok else "error",
        "disk_free_gb": disk_free_gb,
    }
