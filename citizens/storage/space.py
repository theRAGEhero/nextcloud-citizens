# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Free-space guard for the write paths.

Disk usage was only ever *reported* by the health endpoint, never checked
before writing. When the volume filled, a chunk write raised an unhandled
OSError, the phone classified the resulting 500 as transient and retried
silently forever, and the only trace was a stack trace in the log. SQLite
starts failing at the same moment, so the organizer dashboard breaks too.

Refusing the write with an explicit status is better in every way: the phone
still keeps its audio locally and keeps retrying, and the reason is legible.
"""

import shutil
from pathlib import Path

from fastapi import HTTPException

from citizens.logging_setup import get_logger

log = get_logger(__name__)

# Headroom kept for SQLite's WAL, ffmpeg scratch files and the OS. An assembly
# needs a full second copy of one recording while it remuxes, so this is not
# only about the incoming bytes.
MIN_FREE_BYTES = 1024 * 1024 * 1024


def free_bytes(root: Path) -> int:
    try:
        return shutil.disk_usage(root).free
    except OSError:  # unreadable mount: don't block recording on a stat failure
        log.warning("disk_usage_unavailable", exc_info=True)
        return MIN_FREE_BYTES + 1


def has_room_for(root: Path, incoming_bytes: int = 0) -> bool:
    return free_bytes(root) - incoming_bytes >= MIN_FREE_BYTES


def require_room(root: Path, incoming_bytes: int = 0, *, context: str = "") -> None:
    """Raise 507 rather than let a write fail halfway."""
    if has_room_for(root, incoming_bytes):
        return
    log.error(
        "storage_full",
        context=context,
        free_bytes=free_bytes(root),
        needed_bytes=incoming_bytes,
        minimum_bytes=MIN_FREE_BYTES,
    )
    raise HTTPException(
        status_code=507,
        detail="The server is out of storage space — free space or delete old assembly audio",
    )
