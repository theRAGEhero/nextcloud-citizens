"""Job handlers. Each runs inside its own DB session; raising retries the job."""

from sqlalchemy.orm import Session

from citizens.db.models import Recording
from citizens.logging_setup import get_logger
from citizens.services.audio import AudioAssemblyError, assemble_recording
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


HANDLERS = {
    "ASSEMBLE_AUDIO": handle_assemble_audio,
}
