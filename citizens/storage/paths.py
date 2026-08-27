# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Layout of the ExApp's persistent storage.

All Citizens data lives under APP_PERSISTENT_STORAGE (brief §3.3); the app
never touches Nextcloud user files.
"""

from collections.abc import Sequence
from pathlib import Path

SUBDIRS = ("recordings", "assembled", "transcripts", "exports", "temp", "logs")


def ensure_storage_layout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (root / name).mkdir(exist_ok=True)


def db_path(root: Path) -> Path:
    return root / "citizens.db"


def logs_dir(root: Path) -> Path:
    return root / "logs"


def temp_dir(root: Path) -> Path:
    return root / "temp"


def recordings_dir(root: Path) -> Path:
    return root / "recordings"


def recording_dir(root: Path, assembly_id: str, round_id: str, table_id: str, recording_id: str) -> Path:
    """recordings/<assembly>/<round>/<table>/<recording>/ — all path segments are
    server-generated UUIDs, never client input (path-traversal safe by design)."""
    return recordings_dir(root) / assembly_id / round_id / table_id / recording_id


def chunk_path(recording_directory: Path, sequence_number: int) -> Path:
    return recording_directory / "chunks" / f"{sequence_number:06d}.bin"


def assembled_dir(root: Path, assembly_id: str) -> Path:
    return root / "assembled" / assembly_id


def exports_dir(root: Path, assembly_id: str) -> Path:
    """Generated ZIP archives (audio bundle, portable session export)."""
    return root / "exports" / assembly_id


def device_log_path(root: Path, session_id: str) -> Path:
    """Per-recorder-session shipped client logs (JSONL). session_id is a
    server-generated UUID, never client input."""
    return root / "logs" / "devices" / f"{session_id}.jsonl"


def purge_assembly_storage(
    root: Path, assembly_id: str, recorder_session_ids: Sequence[str] = ()
) -> None:
    """Remove every stored file of a deleted assembly (audio chunks, assembled
    canonical audio, transcripts, exports, and the phones' shipped diagnostic
    logs). assembly_id is a server-generated UUID, never client input.

    Device logs live under logs/devices/<session>.jsonl, outside the
    per-assembly tree, so they need their ids passed in — they were previously
    missed and survived deletion as orphaned files nothing could reach.
    """
    import shutil

    for subdir in ("recordings", "assembled", "transcripts", "exports"):
        shutil.rmtree(root / subdir / assembly_id, ignore_errors=True)
    for session_id in recorder_session_ids:
        device_log_path(root, session_id).unlink(missing_ok=True)
