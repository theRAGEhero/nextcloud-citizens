"""Organizer file management: audio inventory, downloads, exports, deletion."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from citizens.db.models import Recording
from citizens.db.session import get_db
from citizens.security.identity import CurrentUser
from citizens.services import files as files_svc
from citizens.services.assemblies import get_owned_assembly
from citizens.services.audit import record_audit_event

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


def _owned_recording(session: Session, recording_id: str, user: str) -> Recording:
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    get_owned_assembly(session, recording.assembly_id, user)
    return recording


@router.get("/assemblies/{assembly_id}/files")
def list_files(assembly_id: str, user: CurrentUser, session: DB):
    assembly = get_owned_assembly(session, assembly_id, user)
    return files_svc.list_files(session, assembly)


@router.get("/recordings/{recording_id}/audio")
def download_audio(recording_id: str, user: CurrentUser, session: DB):
    recording = _owned_recording(session, recording_id, user)
    path = files_svc.canonical_path(recording)
    if path is None:
        detail = (
            "The audio of this recording was deleted"
            if recording.audio_deleted_at
            else "No audio file for this recording"
        )
        raise HTTPException(status_code=404, detail=detail)
    assembly = get_owned_assembly(session, recording.assembly_id, user)
    position = next(
        (r.position for r in assembly.rounds if r.id == recording.round_id), 0
    )
    return FileResponse(
        path,
        media_type=recording.mime_type.split(";")[0] or "audio/webm",
        filename=files_svc.audio_filename(assembly, recording, position),
    )


@router.get("/assemblies/{assembly_id}/audio.zip")
def download_all_audio(assembly_id: str, user: CurrentUser, session: DB):
    assembly = get_owned_assembly(session, assembly_id, user)
    archive = files_svc.build_audio_zip(session, assembly)
    record_audit_event(session, "audio_bundle_downloaded", "assembly", assembly.id, actor=user)
    return _zip_response(archive, f"{_slug(assembly.name)}-audio.zip")


@router.get("/assemblies/{assembly_id}/export.zip")
def download_session_export(assembly_id: str, user: CurrentUser, session: DB):
    assembly = get_owned_assembly(session, assembly_id, user)
    archive = files_svc.build_session_export(session, assembly)
    record_audit_event(session, "session_exported", "assembly", assembly.id, actor=user)
    return _zip_response(archive, f"{_slug(assembly.name)}-session-export.zip")


@router.delete("/recordings/{recording_id}/audio", status_code=200)
def delete_audio(recording_id: str, user: CurrentUser, session: DB):
    recording = _owned_recording(session, recording_id, user)
    freed = files_svc.delete_recording_audio(session, recording)
    record_audit_event(
        session, "recording_audio_deleted", "recording", recording.id, actor=user,
        data={"freed_bytes": freed, "table_number": recording.table_number},
    )
    return {"freed_bytes": freed}


@router.delete("/assemblies/{assembly_id}/audio", status_code=200)
def delete_all_audio(assembly_id: str, user: CurrentUser, session: DB):
    assembly = get_owned_assembly(session, assembly_id, user)
    count, freed = files_svc.delete_assembly_audio(session, assembly)
    record_audit_event(
        session, "assembly_audio_deleted", "assembly", assembly.id, actor=user,
        data={"recordings": count, "freed_bytes": freed},
    )
    return {"recordings": count, "freed_bytes": freed}


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in name)[:40].strip("-") or "assembly"


def _zip_response(archive, filename: str) -> FileResponse:
    # the archive is a throwaway build artifact: stream it, then remove it
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(lambda: archive.unlink(missing_ok=True)),
    )
