# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Organizer transcript API: fetch canonical transcripts, trigger (re)transcription."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from citizens.db.models import Recording, Transcript
from citizens.db.session import get_db
from citizens.security.identity import CurrentUser
from citizens.services.assemblies import get_owned_assembly
from citizens.services.jobs import enqueue_job
from citizens.services.transcription import transcript_payload

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


def _owned_recording(session: Session, recording_id: str, user: str) -> Recording:
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    get_owned_assembly(session, recording.assembly_id, user)  # 404 if not owned
    return recording


@router.get("/recordings/{recording_id}/transcript")
def get_transcript(recording_id: str, user: CurrentUser, session: DB):
    recording = _owned_recording(session, recording_id, user)
    transcript = session.execute(
        select(Transcript).where(Transcript.recording_id == recording.id)
    ).scalar_one_or_none()
    if transcript is None:
        raise HTTPException(status_code=404, detail=f"No transcript yet (recording is {recording.state})")
    return transcript_payload(transcript)


@router.post("/recordings/{recording_id}/transcribe", status_code=202)
def request_transcription(recording_id: str, user: CurrentUser, session: DB):
    """Manual (re)transcription — also recovers jobs that exhausted retries."""
    recording = _owned_recording(session, recording_id, user)
    if recording.state not in ("AUDIO_READY", "TRANSCRIPTION_FAILED", "TRANSCRIBING", "TRANSCRIBED"):
        raise HTTPException(
            status_code=409, detail=f"Recording is {recording.state}; audio must be ready first"
        )
    enqueue_job(session, "TRANSCRIBE_FINAL", {"recording_id": recording.id, "force": True})
    return {"queued": True, "state": recording.state}
