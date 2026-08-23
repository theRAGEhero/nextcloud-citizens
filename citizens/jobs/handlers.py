"""Job handlers. Each runs inside its own DB session; raising retries the job."""

from sqlalchemy.orm import Session

from citizens.db.models import Recording
from citizens.logging_setup import get_logger
from citizens.providers.transcription.base import TranscriptionError
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


HANDLERS = {
    "ASSEMBLE_AUDIO": handle_assemble_audio,
    "TRANSCRIBE_FINAL": handle_transcribe_final,
}
