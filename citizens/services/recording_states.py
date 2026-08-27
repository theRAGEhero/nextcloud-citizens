# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recording state machine (brief §24). Transitions are explicit and resumable."""

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"RECORDING"},
    # → UPLOAD_INCOMPLETE: a phone can die at any point, and leaving the
    # recording in a "healthy pending" state blocks the round's analysis and
    # stops the table re-recording. Giving up is reversible (see below).
    "RECORDING": {"FINALIZING", "UPLOAD_INCOMPLETE"},
    "FINALIZING": {"WAITING_FOR_CHUNKS", "ASSEMBLING", "UPLOAD_INCOMPLETE"},
    "WAITING_FOR_CHUNKS": {"ASSEMBLING", "UPLOAD_INCOMPLETE"},
    "ASSEMBLING": {"AUDIO_READY", "AUDIO_INVALID", "WAITING_FOR_CHUNKS"},
    "AUDIO_READY": {"TRANSCRIBING"},
    "TRANSCRIBING": {"TRANSCRIBED", "TRANSCRIPTION_FAILED"},
    # TRANSCRIBED → TRANSCRIBING supports organizer-requested re-transcription;
    # → AUDIO_READY when the organizer deletes the transcript but keeps the audio
    "TRANSCRIBED": {"ANALYZING", "TRANSCRIBING", "AUDIO_READY"},
    "ANALYZING": {"READY_FOR_REVIEW", "ANALYSIS_FAILED"},
    # READY_FOR_REVIEW → ANALYZING supports organizer-requested re-analysis
    "READY_FOR_REVIEW": {"REVIEWED", "ANALYZING", "AUDIO_READY"},
    # a reviewed recording is otherwise terminal, but deleting its transcript
    # brings it back to plain audio that can be transcribed again
    "REVIEWED": {"AUDIO_READY"},
    # error states are recoverable by retrying the step that failed
    "UPLOAD_INCOMPLETE": {"WAITING_FOR_CHUNKS", "ASSEMBLING"},
    "AUDIO_INVALID": {"ASSEMBLING"},
    "TRANSCRIPTION_FAILED": {"TRANSCRIBING", "AUDIO_READY"},
    "ANALYSIS_FAILED": {"ANALYZING", "AUDIO_READY"},
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
