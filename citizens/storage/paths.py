"""Layout of the ExApp's persistent storage.

All Citizens data lives under APP_PERSISTENT_STORAGE (brief §3.3); the app
never touches Nextcloud user files.
"""

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
