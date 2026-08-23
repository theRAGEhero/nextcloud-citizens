"""Recording state machine (brief §24). Transitions are explicit and resumable."""

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"RECORDING"},
    "RECORDING": {"FINALIZING"},
    "FINALIZING": {"WAITING_FOR_CHUNKS", "ASSEMBLING"},
    "WAITING_FOR_CHUNKS": {"ASSEMBLING", "UPLOAD_INCOMPLETE"},
    "ASSEMBLING": {"AUDIO_READY", "AUDIO_INVALID", "WAITING_FOR_CHUNKS"},
    "AUDIO_READY": {"TRANSCRIBING"},
    "TRANSCRIBING": {"TRANSCRIBED", "TRANSCRIPTION_FAILED"},
    # TRANSCRIBED → TRANSCRIBING supports organizer-requested re-transcription
    "TRANSCRIBED": {"ANALYZING", "TRANSCRIBING"},
    "ANALYZING": {"READY_FOR_REVIEW", "ANALYSIS_FAILED"},
    # READY_FOR_REVIEW → ANALYZING supports organizer-requested re-analysis
    "READY_FOR_REVIEW": {"REVIEWED", "ANALYZING"},
    "REVIEWED": set(),
    # error states are recoverable by retrying the step that failed
    "UPLOAD_INCOMPLETE": {"WAITING_FOR_CHUNKS", "ASSEMBLING"},
    "AUDIO_INVALID": {"ASSEMBLING"},
    "TRANSCRIPTION_FAILED": {"TRANSCRIBING"},
    "ANALYSIS_FAILED": {"ANALYZING"},
}


class InvalidTransition(Exception):
    def __init__(self, current: str, target: str):
        super().__init__(f"Invalid recording state transition {current} -> {target}")
        self.current = current
        self.target = target


def transition(recording, target: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(recording.state, set())
    if target not in allowed:
        raise InvalidTransition(recording.state, target)
    recording.state = target
