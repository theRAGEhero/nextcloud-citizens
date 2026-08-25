"""Public recorder API (PUBLIC AppAPI routes; recorder-session bearer auth).

A recorder session can only ever: read its assembly/round state, create
recordings for its own table, upload chunks, and complete recordings.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from citizens.config import get_settings
from citizens.db.models import Assembly, RecorderSession, Recording
from citizens.db.models.base import utcnow
from citizens.db.session import get_db
from citizens.security.rate_limit import JOIN_LIMITER, client_ip
from citizens.services import recording as rec_svc
from citizens.services.live_captions import LIVE_CAPTIONS
from citizens.services.provider_config import live_stt_snapshot
from citizens.services.recording import RERECORDABLE_STATES
from citizens.storage.paths import device_log_path

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
    result = rec_svc.receive_chunk(session, recording, sequence_number, x_chunk_sha256, body)
    if not result.get("duplicate"):
        # provisional live captions ride on the safety upload — failures here
        # never affect the recording (brief §51)
        assembly = session.get(Assembly, recording.assembly_id)
        LIVE_CAPTIONS.feed(
            recording.id, body, live_stt_snapshot(), assembly.language if assembly else ""
        )
    return result


class CompleteIn(BaseModel):
    total_chunks: int = Field(ge=1, le=100000)


@router.post("/recorder/recordings/{recording_id}/complete")
def complete(
    recording_id: str, data: CompleteIn, recorder_session: RecorderSess, session: DB
):
    recording = rec_svc.get_session_recording(session, recorder_session, recording_id)
    result = rec_svc.complete_recording(session, recording, data.total_chunks)
    if not result["missing_sequences"]:
        LIVE_CAPTIONS.finish(recording.id)
    return result


@router.get("/recorder/recordings/{recording_id}/live")
def live_transcript(recording_id: str, recorder_session: RecorderSess, session: DB):
    """Provisional live captions for this table's recording (may be empty or
    unavailable — that is never an error)."""
    recording = rec_svc.get_session_recording(session, recorder_session, recording_id)
    return LIVE_CAPTIONS.status(recording.id)


@router.get("/recorder/recordings/{recording_id}")
def recording_status(recording_id: str, recorder_session: RecorderSess, session: DB):
    recording = rec_svc.get_session_recording(session, recorder_session, recording_id)
    return rec_svc.recording_status(session, recording)


def _published_report(session: Session, recorder_session: RecorderSession) -> tuple:
    from citizens.services.lifecycle import frozen_report
    from citizens.services.report import build_report

    assembly = session.get(Assembly, recorder_session.assembly_id)
    if assembly is None or not _report_available(session, assembly):
        raise HTTPException(status_code=404, detail="No published report for this assembly")
    # once the session was closed, participants read the frozen version — a
    # later reopening must never change the report under them
    snapshot = frozen_report(assembly)
    if snapshot is not None:
        return assembly, snapshot
    # approved findings only — AI drafts never reach participants
    return assembly, build_report(session, assembly, include_drafts=False)


@router.get("/recorder/report")
def published_report(recorder_session: RecorderSess, session: DB):
    _, report = _published_report(session, recorder_session)
    return report


@router.get("/recorder/report.pdf")
def published_report_pdf(recorder_session: RecorderSess, session: DB):
    from fastapi.responses import Response

    from citizens.services.branding import logo_path, organization_name
    from citizens.services.report_pdf import render_pdf

    assembly, report = _published_report(session, recorder_session)
    filename = f"{assembly.name[:40].replace(' ', '-')}-report.pdf"
    return Response(
        render_pdf(report, logo_path(), organization_name()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class HeartbeatIn(BaseModel):
    recording_id: str | None = None
    recording_active: bool = False
    armed: bool = False
    local_chunks: int = Field(default=0, ge=0)
    acked_chunks: int = Field(default=0, ge=0)
    storage_ok: bool = True
    storage_free_mb: float | None = None


@router.post("/recorder/heartbeat")
def heartbeat(data: HeartbeatIn, recorder_session: RecorderSess, session: DB):
    recorder_session.last_status_json = data.model_dump_json()
    recorder_session.last_status_at = utcnow()
    return {"ok": True}


class LogEntry(BaseModel):
    ts: float
    level: str = Field(max_length=10)
    event: str = Field(max_length=120)
    data: dict | None = None


class LogsIn(BaseModel):
    entries: list[LogEntry] = Field(max_length=200)


MAX_DEVICE_LOG_BYTES = 5 * 1024 * 1024


@router.post("/recorder/logs")
def ship_logs(data: LogsIn, recorder_session: RecorderSess):
    """Offline-tolerant client log shipping — the recorder's diagnostic trail
    for devices nobody can attach devtools to."""
    path = device_log_path(get_settings().app_persistent_storage, recorder_session.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > MAX_DEVICE_LOG_BYTES:
        return {"accepted": 0, "truncated": True}
    with path.open("a", encoding="utf-8") as handle:
        for entry in data.entries:
            line = json.dumps(entry.model_dump(exclude_none=True))[:2048]
            handle.write(line + "\n")
    return {"accepted": len(data.entries), "truncated": False}


def _assembly_state(session: Session, recorder_session: RecorderSession) -> dict:
    assembly = session.get(Assembly, recorder_session.assembly_id)
    if assembly is None:
        raise HTTPException(status_code=404, detail="Assembly not found")
    # this table's recording state per round, so the phone can lock finished
    # rounds and offer only un-recorded ones — plus this table's own AI
    # summary once analysis lands (shown on the final screen)
    recorded_rounds: dict[str, str] = {}
    table_summaries: dict[str, str] = {}
    for recording in session.execute(
        select(Recording).where(
            Recording.assembly_id == assembly.id,
            Recording.table_number == recorder_session.table_number,
            Recording.state.notin_(RERECORDABLE_STATES),
        )
    ).scalars():
        recorded_rounds[recording.round_id] = recording.state
        if recording.analysis_summary:
            table_summaries[recording.round_id] = recording.analysis_summary
    return {
        "assembly": {
            "id": assembly.id,
            "name": assembly.name,
            "language": assembly.language,
            "recording_mode": assembly.recording_mode,
        },
        # phones learn about report availability through the status poll
        "report_available": _report_available(session, assembly),
        "table_number": recorder_session.table_number,
        "rounds": [
            {
                "id": round_.id,
                "position": round_.position,
                "title": round_.title,
                "question": round_.question,
                "duration_minutes": round_.duration_minutes,
                "status": round_.status,
                "recorded_state": recorded_rounds.get(round_.id),
                "table_summary": table_summaries.get(round_.id, ""),
            }
            for round_ in assembly.rounds
        ],
    }


def _report_available(session: Session, assembly: Assembly) -> bool:
    """Published explicitly — or, for independent assemblies, every table has
    completed every round (the organizer may still publish earlier)."""
    if assembly.report_published_at is not None:
        return True
    if assembly.recording_mode != "independent":
        return False
    # a closed session with a frozen report stays readable through a reopen
    if assembly.final_report_json:
        return True
    return rec_svc.assembly_complete(session, assembly)
