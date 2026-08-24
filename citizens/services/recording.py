"""Recorder sessions, recordings and chunk intake (brief §14, §17, §23)."""

import hashlib
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from citizens.config import get_settings
from citizens.db.models import RecorderSession, Recording, Round, Table
from citizens.db.models.base import utcnow
from citizens.db.models.recording import AudioChunk
from citizens.logging_setup import get_logger
from citizens.security.recorder_tokens import generate_token, hash_token
from citizens.services import invites as invite_svc
from citizens.services import provider_config
from citizens.services.jobs import enqueue_job
from citizens.services.recording_states import transition
from citizens.storage.paths import chunk_path, recording_dir

log = get_logger(__name__)

SESSION_LIFETIME_HOURS = 16
MAX_CHUNK_BYTES = 5 * 1024 * 1024


def create_session_from_invite(session: Session, token: str) -> tuple[RecorderSession, str]:
    invite = invite_svc.find_active_by_token(session, token)
    if invite is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked invite")
    invite.last_used_at = utcnow()
    bearer = generate_token()
    recorder_session = RecorderSession(
        invite_id=invite.id,
        assembly_id=invite.assembly_id,
        table_number=invite.table_number,
        token_hash=hash_token(bearer),
        expires_at=utcnow() + timedelta(hours=SESSION_LIFETIME_HOURS),
    )
    session.add(recorder_session)
    session.flush()
    log.info(
        "recorder_session_created",
        assembly_id=invite.assembly_id,
        table_number=invite.table_number,
    )
    return recorder_session, bearer


def get_session_by_bearer(session: Session, bearer: str) -> RecorderSession:
    recorder_session = session.execute(
        select(RecorderSession).where(RecorderSession.token_hash == hash_token(bearer))
    ).scalar_one_or_none()
    if (
        recorder_session is None
        or recorder_session.revoked_at is not None
        or recorder_session.expires_at < utcnow()
    ):
        raise HTTPException(status_code=401, detail="Recorder session invalid or expired")
    recorder_session.last_seen_at = utcnow()
    return recorder_session


# a recording in one of these states is failed/abandoned: re-recording allowed
RERECORDABLE_STATES = ("CREATED", "AUDIO_INVALID", "UPLOAD_INCOMPLETE")

# the audio is validated and safe server-side (assembly onward)
COMPLETED_STATES = (
    "AUDIO_READY", "TRANSCRIBING", "TRANSCRIBED", "TRANSCRIPTION_FAILED",
    "ANALYZING", "READY_FOR_REVIEW", "REVIEWED", "ANALYSIS_FAILED",
)


def assembly_complete(session: Session, assembly) -> bool:
    """True when EVERY table has a completed recording for EVERY round.

    Drives the independent-mode auto-availability of the report on phones:
    with analysis enabled, every round must also carry its cross-table AI
    summary so the auto-shown report is never empty."""
    expected = set(range(1, assembly.default_table_count + 1))
    if not expected or not assembly.rounds:
        return False
    completed_by_round: dict[str, set[int]] = {}
    for recording in session.execute(
        select(Recording).where(
            Recording.assembly_id == assembly.id,
            Recording.state.in_(COMPLETED_STATES),
        )
    ).scalars():
        completed_by_round.setdefault(recording.round_id, set()).add(recording.table_number)
    analysis_on = provider_config.analysis_enabled_cached()
    for round_ in assembly.rounds:
        if not expected.issubset(completed_by_round.get(round_.id, set())):
            return False
        if analysis_on and not round_.analysis_summary:
            return False
    return True


def start_recording(
    session: Session, recorder_session: RecorderSession, round_id: str, mime_type: str
) -> Recording:
    round_ = session.get(Round, round_id)
    if round_ is None or round_.assembly_id != recorder_session.assembly_id:
        raise HTTPException(status_code=404, detail="Round not found")
    table = session.execute(
        select(Table).where(Table.round_id == round_id, Table.number == recorder_session.table_number)
    ).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=422, detail="This round has no table with your number")

    # orchestrated assemblies record only while the facilitator has the round
    # open; independent assemblies let each table record on its own schedule
    if round_.assembly.recording_mode == "orchestrated" and round_.status != "ACTIVE":
        raise HTTPException(
            status_code=409, detail="The facilitator has not started this round yet"
        )

    # one healthy recording per table+round: prevents accidental extra
    # recordings after a table already finished (unless the earlier attempt failed)
    existing = session.execute(
        select(Recording).where(
            Recording.round_id == round_id,
            Recording.table_id == table.id,
            Recording.state.notin_(RERECORDABLE_STATES),
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"This table already recorded round {round_.position} "
            f"(recording is {existing.state}). Ask the facilitator if a re-recording is needed.",
        )

    recording = Recording(
        assembly_id=recorder_session.assembly_id,
        round_id=round_id,
        table_id=table.id,
        table_number=recorder_session.table_number,
        recorder_session_id=recorder_session.id,
        state="CREATED",  # column defaults only apply at flush; transition() needs it now
        mime_type=mime_type[:80],
        started_at=utcnow(),
    )
    transition(recording, "RECORDING")
    session.add(recording)
    session.flush()
    log.info(
        "recording_started",
        recording_id=recording.id,
        round_id=round_id,
        table_number=recorder_session.table_number,
        mime_type=recording.mime_type,
    )
    return recording


def get_session_recording(
    session: Session, recorder_session: RecorderSession, recording_id: str
) -> Recording:
    recording = session.get(Recording, recording_id)
    if (
        recording is None
        or recording.assembly_id != recorder_session.assembly_id
        or recording.table_number != recorder_session.table_number
    ):
        raise HTTPException(status_code=404, detail="Recording not found")
    return recording


def receive_chunk(
    session: Session,
    recording: Recording,
    sequence_number: int,
    client_sha256: str,
    data: bytes,
) -> dict:
    """Store one chunk. Idempotent on (recording, sequence, sha256)."""
    if recording.state not in ("RECORDING", "FINALIZING", "WAITING_FOR_CHUNKS"):
        raise HTTPException(status_code=409, detail=f"Recording is {recording.state}")
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty chunk")
    if len(data) > MAX_CHUNK_BYTES:
        raise HTTPException(status_code=413, detail="Chunk too large")

    actual = hashlib.sha256(data).hexdigest()
    if actual != client_sha256.lower():
        raise HTTPException(status_code=400, detail="Checksum mismatch")

    existing = session.execute(
        select(AudioChunk).where(
            AudioChunk.recording_id == recording.id,
            AudioChunk.sequence_number == sequence_number,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.sha256 == actual:
            # duplicate upload of the identical chunk: idempotent ACK
            return {"acknowledged": True, "duplicate": True, "sequence_number": sequence_number}
        raise HTTPException(status_code=409, detail="Sequence already stored with different content")

    root = get_settings().app_persistent_storage
    directory = recording_dir(
        root, recording.assembly_id, recording.round_id, recording.table_id, recording.id
    )
    target = chunk_path(directory, sequence_number)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    session.add(
        AudioChunk(
            recording_id=recording.id,
            sequence_number=sequence_number,
            sha256=actual,
            size_bytes=len(data),
            path=str(target.relative_to(root)),
        )
    )
    recording.received_chunks = recording.received_chunks + 1
    session.flush()
    log.info(
        "recording_chunk_received",
        recording_id=recording.id,
        sequence_number=sequence_number,
        size_bytes=len(data),
    )
    return {"acknowledged": True, "duplicate": False, "sequence_number": sequence_number}


def missing_sequences(session: Session, recording: Recording) -> list[int]:
    if recording.total_chunks is None:
        return []
    stored = {
        row
        for row in session.execute(
            select(AudioChunk.sequence_number).where(AudioChunk.recording_id == recording.id)
        ).scalars()
    }
    return [seq for seq in range(recording.total_chunks) if seq not in stored]


def complete_recording(session: Session, recording: Recording, total_chunks: int) -> dict:
    if recording.state == "RECORDING":
        transition(recording, "FINALIZING")
    elif recording.state not in ("FINALIZING", "WAITING_FOR_CHUNKS"):
        raise HTTPException(status_code=409, detail=f"Recording is {recording.state}")

    recording.total_chunks = total_chunks
    recording.ended_at = recording.ended_at or utcnow()
    missing = missing_sequences(session, recording)
    if missing:
        transition(recording, "WAITING_FOR_CHUNKS")
        log.info(
            "recording_waiting_for_chunks",
            recording_id=recording.id,
            missing=len(missing),
        )
        return {"state": recording.state, "missing_sequences": missing}

    transition(recording, "ASSEMBLING")
    enqueue_job(session, "ASSEMBLE_AUDIO", {"recording_id": recording.id})
    log.info("recording_completed", recording_id=recording.id, total_chunks=total_chunks)
    return {"state": recording.state, "missing_sequences": []}


def recording_status(session: Session, recording: Recording) -> dict:
    return {
        "recording_id": recording.id,
        "state": recording.state,
        "received_chunks": recording.received_chunks,
        "total_chunks": recording.total_chunks,
        "missing_sequences": missing_sequences(session, recording)
        if recording.state in ("WAITING_FOR_CHUNKS", "UPLOAD_INCOMPLETE")
        else [],
        "error_code": recording.error_code,
        "duration_seconds": recording.duration_seconds,
    }
