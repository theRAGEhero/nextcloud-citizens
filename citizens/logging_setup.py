# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured logging foundation.

Two sinks:
- console: pretty + colored in dev (CITIZENS_DEV=1), JSON otherwise;
- rotating JSON-lines file at <APP_PERSISTENT_STORAGE>/logs/citizens.jsonl.

Every event dict passes a redaction processor before it is rendered, so
secrets never reach either sink even if a caller logs them by mistake.
"""

import logging
import logging.handlers
import re

import structlog

from citizens.config import Settings
from citizens.storage.paths import logs_dir

SENSITIVE_KEY_RE = re.compile(
    r"secret|token|passw|api[_-]?key|apikey|authorization|bearer|credential|cookie", re.IGNORECASE
)
REDACTED = "[REDACTED]"


def _redact(value):
    if isinstance(value, dict):
        return {
            key: (REDACTED if SENSITIVE_KEY_RE.search(str(key)) else _redact(val))
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def redaction_processor(_logger, _method_name, event_dict: dict) -> dict:
    return _redact(event_dict)


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.citizens_log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        redaction_processor,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    file_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )
    if settings.citizens_dev:
        console_renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        console_renderer = structlog.processors.JSONRenderer()
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            console_renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    log_path = logs_dir(settings.app_persistent_storage) / "citizens.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(file_formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.setLevel(level)

    # We emit our own request-completion events; uvicorn's access log is noise.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str = "citizens") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
