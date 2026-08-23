"""Job handlers. Each runs inside its own DB session; raising retries the job."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from citizens.db.models import AppJob, Recording, Round
from citizens.logging_setup import get_logger
from citizens.providers.analysis.openai_compat import AnalysisError
from citizens.providers.transcription.base import TranscriptionError
from citizens.services import analysis as analysis_svc
from citizens.services import provider_config
from citizens.services import transcription as transcription_svc
from citizens.services.audio import AudioAssemblyError, assemble_recording
from citizens.services.jobs import enqueue_job
from citizens.services.recording_states import transition

log = get_logger(__name__)


class PermanentJobError(Exception):
    """Raised when retrying cannot help; the job goes straight to FAILED."""


def handle_assemble_audio(session: Session, payload: dict) -> None:
    recording = session.get(Recording, payload["recording_id"])
    if recording is None:
        raise PermanentJobError(f"Recording {payload['recording_id']} no longer exists")
    if recording.state == "AUDIO_READY":
        return  # already done (job retried after success)
    if recording.state != "ASSEMBLING":
        transition(recording, "ASSEMBLING")
    try:
        assemble_recording(session, recording)
    except AudioAssemblyError as exc:
        recording.error_code = exc.code
        transition(recording, "AUDIO_INVALID")
        log.error("audio_assembly_failed", recording_id=recording.id, error_code=exc.code)
        raise PermanentJobError(str(exc)) from exc

    _maybe_enqueue_transcription(session, recording)


def _maybe_enqueue_transcription(session: Session, recording: Recording) -> None:
    try:
        store = provider_config.default_store()
        if transcription_svc.batch_transcription_ready(store):
            enqueue_job(session, "TRANSCRIBE_FINAL", {"recording_id": recording.id})
            log.info("transcription_enqueued", recording_id=recording.id)
    except Exception:
        # never let STT config problems endanger the assembled audio
        log.warning("transcription_enqueue_failed", recording_id=recording.id, exc_info=True)


def handle_transcribe_final(session: Session, payload: dict) -> None:
    recording = session.get(Recording, payload["recording_id"])
    if recording is None:
        raise PermanentJobError(f"Recording {payload['recording_id']} no longer exists")
    if recording.state == "TRANSCRIBED" and not payload.get("force"):
        return
    if recording.state in ("AUDIO_READY", "TRANSCRIPTION_FAILED", "TRANSCRIBED"):
        transition(recording, "TRANSCRIBING")
    elif recording.state != "TRANSCRIBING":
        raise PermanentJobError(f"Recording is {recording.state}; cannot transcribe")

    store = provider_config.default_store()
    try:
        transcription_svc.transcribe_recording(session, store, recording)
    except TranscriptionError as exc:
        recording.error_code = "TRANSCRIPTION_FAILED"
        transition(recording, "TRANSCRIPTION_FAILED")
        log.error("stt_failed", recording_id=recording.id, permanent=exc.permanent)
        if exc.permanent:
            raise PermanentJobError(str(exc)) from exc
        raise  # temporary (429/5xx/network) → job retry with backoff
    recording.error_code = ""
    transition(recording, "TRANSCRIBED")
    _maybe_enqueue_analysis(session, recording)


def _maybe_enqueue_analysis(session: Session, recording: Recording) -> None:
    try:
        store = provider_config.default_store()
        if analysis_svc.analysis_ready(store):
            enqueue_job(session, "ANALYZE_TABLE", {"recording_id": recording.id})
            log.info("analysis_enqueued", recording_id=recording.id)
    except Exception:
        log.warning("analysis_enqueue_failed", recording_id=recording.id, exc_info=True)


def handle_analyze_table(session: Session, payload: dict) -> None:
    recording = session.get(Recording, payload["recording_id"])
    if recording is None:
        raise PermanentJobError(f"Recording {payload['recording_id']} no longer exists")
    if recording.state == "READY_FOR_REVIEW" and not payload.get("force"):
        return
    if recording.state in ("TRANSCRIBED", "ANALYSIS_FAILED", "READY_FOR_REVIEW"):
        transition(recording, "ANALYZING")
    elif recording.state != "ANALYZING":
        raise PermanentJobError(f"Recording is {recording.state}; cannot analyze")

    store = provider_config.default_store()
    try:
        analysis_svc.analyze_table(session, store, recording)
    except AnalysisError as exc:
        recording.error_code = "ANALYSIS_FAILED"
        transition(recording, "ANALYSIS_FAILED")
        log.error("analysis_failed", recording_id=recording.id, permanent=exc.permanent)
        if exc.permanent:
            raise PermanentJobError(str(exc)) from exc
        raise
    recording.error_code = ""
    transition(recording, "READY_FOR_REVIEW")
    _maybe_enqueue_round_analysis(session, recording)


def _maybe_enqueue_round_analysis(session: Session, recording: Recording) -> None:
    """When the last analyzed table of the round is done, cluster cross-table."""
    states = [
        row
        for row in session.execute(
            select(Recording.state).where(Recording.round_id == recording.round_id)
        ).scalars()
    ]
    healthy_pending = {
        "CREATED", "RECORDING", "FINALIZING", "WAITING_FOR_CHUNKS", "ASSEMBLING",
        "AUDIO_READY", "TRANSCRIBING", "TRANSCRIBED", "ANALYZING",
    }
    if any(state in healthy_pending for state in states):
        return
    payload = json.dumps({"round_id": recording.round_id})
    already = session.execute(
        select(AppJob).where(
            AppJob.type == "ANALYZE_ROUND",
            AppJob.state.in_(("QUEUED", "RUNNING", "RETRY")),
            AppJob.payload_json == payload,
        )
    ).scalar_one_or_none()
    if already is None:
        enqueue_job(session, "ANALYZE_ROUND", {"round_id": recording.round_id})
        log.info("round_analysis_enqueued", round_id=recording.round_id)


def handle_analyze_round(session: Session, payload: dict) -> None:
    round_ = session.get(Round, payload["round_id"])
    if round_ is None:
        raise PermanentJobError(f"Round {payload['round_id']} no longer exists")
    store = provider_config.default_store()
    try:
        analysis_svc.analyze_round(session, store, round_)
    except AnalysisError as exc:
        log.error("analysis_failed", round_id=round_.id, permanent=exc.permanent)
        if exc.permanent:
            raise PermanentJobError(str(exc)) from exc
        raise
    if round_.status in ("ENDED", "PROCESSING"):
        round_.status = "READY_FOR_REVIEW"


HANDLERS = {
    "ASSEMBLE_AUDIO": handle_assemble_audio,
    "TRANSCRIBE_FINAL": handle_transcribe_final,
    "ANALYZE_TABLE": handle_analyze_table,
    "ANALYZE_ROUND": handle_analyze_round,
}
