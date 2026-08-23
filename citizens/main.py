"""Nextcloud Citizens ExApp entry point."""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from nc_py_api import AsyncNextcloudApp
from nc_py_api.ex_app import AppAPIAuthMiddleware, run_app, set_handlers
from structlog.contextvars import bind_contextvars, clear_contextvars

from citizens.api.system import router as system_router
from citizens.config import get_settings
from citizens.db.migrate import run_migrations
from citizens.db.session import configure_database, sqlite_url
from citizens.logging_setup import get_logger, setup_logging
from citizens.services.audit import record_audit_event
from citizens.storage.paths import db_path, ensure_storage_layout

log = get_logger(__name__)


async def enabled_handler(enabled: bool, nc: AsyncNextcloudApp) -> str:
    try:
        if enabled:
            await nc.ui.top_menu.register("citizens", "Citizens", "img/app.svg")
            await nc.ui.resources.set_script("top_menu", "citizens", "js/citizens-main")
            record_audit_event("app_enabled")
            log.info("app_enabled")
        else:
            record_audit_event("app_disabled")
            log.info("app_disabled")
    except Exception as exc:
        log.error("enabled_handler_failed", enabled=enabled, exc_info=True)
        return str(exc)
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_storage_layout(settings.app_persistent_storage)
    setup_logging(settings)
    configure_database(sqlite_url(db_path(settings.app_persistent_storage)))
    run_migrations(sqlite_url(db_path(settings.app_persistent_storage)))
    set_handlers(app, enabled_handler)
    log.info("app_started", version=settings.app_version, storage=str(settings.app_persistent_storage))
    yield
    log.info("app_stopping")


def create_app(with_auth: bool = True) -> FastAPI:
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    if with_auth:
        app.add_middleware(AppAPIAuthMiddleware)

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        if request.url.path == "/heartbeat":
            return await call_next(request)
        clear_contextvars()
        bind_contextvars(request_id=uuid.uuid4().hex[:12])
        started = time.monotonic()
        response = await call_next(request)
        log.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.monotonic() - started) * 1000, 1),
        )
        return response

    app.include_router(system_router, prefix="/api/v1")
    return app


APP = create_app()


if __name__ == "__main__":
    run_app("citizens.main:APP", log_level="info")
