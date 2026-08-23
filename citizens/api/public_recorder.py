"""Public recorder API (PUBLIC AppAPI routes; recorder-session bearer auth).

A recorder session can only ever: read its assembly/round state, create
recordings for its own table, upload chunks, and complete recordings.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from citizens.db.models import Assembly, RecorderSession
from citizens.db.session import get_db
from citizens.security.rate_limit import JOIN_LIMITER, client_ip
from citizens.services import recording as rec_svc

router = APIRouter(prefix="/public")

DB = Annotated[Session, Depends(get_db)]


def get_recorder_session(
    session: DB,
    authorization: Annotated[str, Header()] = "",
) -> RecorderSession:
    scheme, _, bearer = authorization.partition(" ")
    if scheme.lower() != "bearer" or not bearer:
        raise HTTPException(status_code=401, detail="Missing recorder session token")
    return rec_svc.get_session_by_bearer(session, bearer.strip())


RecorderSess = Annotated[RecorderSession, Depends(get_recorder_session)]


class JoinIn(BaseModel):
    token: str = Field(min_length=16, max_length=128)


@router.post("/join")
def join(data: JoinIn, request: Request, session: DB):
    JOIN_LIMITER.check(client_ip(request))
    recorder_session, bearer = rec_svc.create_session_from_invite(session, data.token)
    return {
        "session_token": bearer,
        "expires_at": recorder_session.expires_at,
        **_assembly_state(session, recorder_session),
    }


@router.get("/recorder/status")
def status(recorder_session: RecorderSess, session: DB):
    return _assembly_state(session, recorder_session)


class StartIn(BaseModel):
    round_id: str
    mime_type: str = Field(min_length=1, max_length=80)


@router.post("/recorder/start", status_code=201)
def start(data: StartIn, recorder_session: RecorderSess, session: DB):
    recording = rec_svc.start_recording(session, recorder_session, data.round_id, data.mime_type)
    return {"recording_id": recording.id, "state": recording.state}


@router.post("/recorder/recordings/{recording_id}/chunks/{sequence_number}")
async def upload_chunk(
    recording_id: str,
    sequence_number: int,
    request: Request,
    recorder_session: RecorderSess,
    session: DB,
    x_chunk_sha256: Annotated[str, Header()] = "",
):
    if not x_chunk_sha256:
        raise HTTPException(status_code=400, detail="X-Chunk-SHA256 header required")
    if sequence_number < 0 or sequence_number > 100000:
        raise HTTPException(status_code=422, detail="Invalid sequence number")
    body = await request.body()
    recording = rec_svc.get_session_recording(session, recorder_session, recording_id)
    return rec_svc.receive_chunk(session, recording, sequence_number, x_chunk_sha256, body)


class CompleteIn(BaseModel):
    total_chunks: int = Field(ge=1, le=100000)


@router.post("/recorder/recordings/{recording_id}/complete")
def complete(
    recording_id: str, data: CompleteIn, recorder_session: RecorderSess, session: DB
):
    recording = rec_svc.get_session_recording(session, recorder_session, recording_id)
    return rec_svc.complete_recording(session, recording, data.total_chunks)


@router.get("/recorder/recordings/{recording_id}")
def recording_status(recording_id: str, recorder_session: RecorderSess, session: DB):
    recording = rec_svc.get_session_recording(session, recorder_session, recording_id)
    return rec_svc.recording_status(session, recording)


def _assembly_state(session: Session, recorder_session: RecorderSession) -> dict:
    assembly = session.get(Assembly, recorder_session.assembly_id)
    if assembly is None:
        raise HTTPException(status_code=404, detail="Assembly not found")
    return {
        "assembly": {"id": assembly.id, "name": assembly.name, "language": assembly.language},
        "table_number": recorder_session.table_number,
        "rounds": [
            {
                "id": round_.id,
                "position": round_.position,
                "title": round_.title,
                "question": round_.question,
                "duration_minutes": round_.duration_minutes,
                "status": round_.status,
            }
            for round_ in assembly.rounds
        ],
    }
