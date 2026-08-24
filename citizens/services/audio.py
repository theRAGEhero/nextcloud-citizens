"""Audio assembly and validation (brief §23).

Chunks from one continuous MediaRecorder session concatenate into a valid
stream; ffmpeg then remuxes it into a clean container (fixing metadata like
missing duration) without re-encoding.
"""

import hashlib
import json
import subprocess

from sqlalchemy.orm import Session

from citizens.config import get_settings
from citizens.db.models import Recording
from citizens.logging_setup import get_logger
from citizens.services.recording import missing_sequences
from citizens.services.recording_states import transition
from citizens.storage.paths import assembled_dir, recording_dir, temp_dir

log = get_logger(__name__)

EXTENSION_BY_MIME = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
}


class AudioAssemblyError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _extension_for(mime_type: str) -> str:
    base = mime_type.split(";")[0].strip().lower()
    return EXTENSION_BY_MIME.get(base, ".webm")


def assemble_recording(session: Session, recording: Recording) -> None:
    """Concatenate chunks, validate with ffprobe, remux, checksum, mark AUDIO_READY."""
    missing = missing_sequences(session, recording)
    if missing:
        transition(recording, "WAITING_FOR_CHUNKS")
        log.warning("audio_assemble_missing_chunks", recording_id=recording.id, missing=len(missing))
        return

    root = get_settings().app_persistent_storage
    directory = recording_dir(
        root, recording.assembly_id, recording.round_id, recording.table_id, recording.id
    )
    extension = _extension_for(recording.mime_type)
    raw_path = temp_dir(root) / f"{recording.id}-raw{extension}"
    canonical = assembled_dir(root, recording.assembly_id) / f"{recording.id}{extension}"
    canonical.parent.mkdir(parents=True, exist_ok=True)

    chunks = sorted(recording.chunks, key=lambda c: c.sequence_number)
    # release the DB write lock before file/ffmpeg work: the job session
    # otherwise holds SQLite's single writer slot for the whole assembly,
    # 500-ing every API request after busy_timeout (expire_on_commit=False
    # keeps the loaded chunk rows usable)
    session.commit()
    digest = hashlib.sha256()
    with open(raw_path, "wb") as raw:
        for chunk in chunks:
            data = (root / chunk.path).read_bytes()
            if hashlib.sha256(data).hexdigest() != chunk.sha256:
                raw_path.unlink(missing_ok=True)
                raise AudioAssemblyError(
                    "CHUNK_CORRUPTED", f"Chunk {chunk.sequence_number} failed checksum on disk"
                )
            raw.write(data)
            digest.update(data)

    try:
        probe = _ffprobe(raw_path)
        _remux(raw_path, canonical)
        final_probe = _ffprobe(canonical)
    except AudioAssemblyError:
        raise
    finally:
        raw_path.unlink(missing_ok=True)

    recording.canonical_audio_path = str(canonical.relative_to(root))
    recording.duration_seconds = final_probe.get("duration") or probe.get("duration")
    recording.sha256 = hashlib.sha256(canonical.read_bytes()).hexdigest()
    recording.error_code = ""
    transition(recording, "AUDIO_READY")
    log.info(
        "audio_assembled",
        recording_id=recording.id,
        duration_seconds=recording.duration_seconds,
        size_bytes=canonical.stat().st_size,
    )
    _write_manifest(directory, recording, chunks)


def _write_manifest(directory, recording: Recording, chunks) -> None:
    manifest = {
        "recording_id": recording.id,
        "mime_type": recording.mime_type,
        "total_chunks": recording.total_chunks,
        "canonical_audio_path": recording.canonical_audio_path,
        "sha256": recording.sha256,
        "duration_seconds": recording.duration_seconds,
        "chunks": [
            {"sequence": c.sequence_number, "sha256": c.sha256, "size": c.size_bytes} for c in chunks
        ],
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=1))


def _ffprobe(path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise AudioAssemblyError("AUDIO_INVALID", f"ffprobe failed: {result.stderr[-500:]}")
    info = json.loads(result.stdout or "{}")
    streams = info.get("streams", [])
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise AudioAssemblyError("AUDIO_INVALID", "No audio stream found")
    duration = info.get("format", {}).get("duration")
    return {"duration": float(duration) if duration else None}


def _remux(source, target) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-c", "copy", str(target)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        raise AudioAssemblyError("AUDIO_INVALID", f"ffmpeg remux failed: {result.stderr[-500:]}")
