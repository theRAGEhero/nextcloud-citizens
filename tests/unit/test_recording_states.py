import pytest

from citizens.services.recording_states import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    transition,
)


class FakeRecording:
    def __init__(self, state: str):
        self.state = state


def test_happy_path_to_reviewed():
    recording = FakeRecording("CREATED")
    for target in (
        "RECORDING", "FINALIZING", "ASSEMBLING", "AUDIO_READY",
        "TRANSCRIBING", "TRANSCRIBED", "ANALYZING", "READY_FOR_REVIEW", "REVIEWED",
    ):
        transition(recording, target)
    assert recording.state == "REVIEWED"


def test_missing_chunk_detour():
    recording = FakeRecording("FINALIZING")
    transition(recording, "WAITING_FOR_CHUNKS")
    transition(recording, "ASSEMBLING")
    assert recording.state == "ASSEMBLING"


def test_error_states_are_recoverable():
    recording = FakeRecording("ASSEMBLING")
    transition(recording, "AUDIO_INVALID")
    transition(recording, "ASSEMBLING")
    assert recording.state == "ASSEMBLING"

    recording = FakeRecording("TRANSCRIBING")
    transition(recording, "TRANSCRIPTION_FAILED")
    transition(recording, "TRANSCRIBING")
    assert recording.state == "TRANSCRIBING"


def test_invalid_transitions_raise():
    with pytest.raises(InvalidTransition):
        transition(FakeRecording("CREATED"), "AUDIO_READY")
    with pytest.raises(InvalidTransition):
        transition(FakeRecording("REVIEWED"), "RECORDING")


def test_every_state_is_reachable_or_initial():
    reachable = {target for targets in ALLOWED_TRANSITIONS.values() for target in targets}
    for state in ALLOWED_TRANSITIONS:
        assert state == "CREATED" or state in reachable, f"{state} is unreachable"
