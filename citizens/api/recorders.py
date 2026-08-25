# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Organizer API for recorder invites/QR codes and device diagnostics."""

from collections import deque
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from citizens.config import get_settings
from citizens.db.models import RecorderSession
from citizens.db.session import get_db
from citizens.domain import schemas
from citizens.security.identity import CurrentUser
from citizens.services import invites as invite_svc
from citizens.services.assemblies import get_owned_assembly
from citizens.services.audit import record_audit_event
from citizens.storage.paths import device_log_path

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


@router.get("/assemblies/{assembly_id}/invites", response_model=list[schemas.InviteOut])
def list_invites(assembly_id: str, user: CurrentUser, session: DB):
    get_owned_assembly(session, assembly_id, user)
    return invite_svc.list_invites(session, assembly_id)


@router.get(
    "/assemblies/{assembly_id}/invites/links",
    response_model=list[schemas.InviteGenerated],
)
def invite_links(assembly_id: str, user: CurrentUser, session: DB):
    """Re-materialized QR sheet for the active invites (tokens are stored
    encrypted with the app secret; invites from before that existed are
    omitted and need a regenerate)."""
    assembly = get_owned_assembly(session, assembly_id, user)
    return invite_svc.invite_links(session, assembly)


@router.post(
    "/assemblies/{assembly_id}/invites/generate",
    response_model=list[schemas.InviteGenerated],
    status_code=201,
)
def generate_invites(assembly_id: str, user: CurrentUser, session: DB):
    """Returns fresh invite URLs + QR SVGs.
    Any previously active invites for this assembly are revoked."""
    assembly = get_owned_assembly(session, assembly_id, user)
    generated = invite_svc.generate_invites(session, assembly)
    record_audit_event(
        session, "invites_generated", "assembly", assembly.id, actor=user, data={"count": len(generated)}
    )
    return generated


@router.post("/assemblies/{assembly_id}/invites/revoke", status_code=204)
def revoke_invites(assembly_id: str, user: CurrentUser, session: DB):
    assembly = get_owned_assembly(session, assembly_id, user)
    count = invite_svc.revoke_invites(session, assembly.id)
    record_audit_event(
        session, "invites_revoked", "assembly", assembly.id, actor=user, data={"count": count}
    )


@router.get("/assemblies/{assembly_id}/tables/{table_number}/device-logs")
def device_logs(
    assembly_id: str,
    table_number: int,
    user: CurrentUser,
    session: DB,
    tail: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    """Tail of the latest device's shipped client log for one table."""
    get_owned_assembly(session, assembly_id, user)
    recorder_session = session.execute(
        select(RecorderSession)
        .where(
            RecorderSession.assembly_id == assembly_id,
            RecorderSession.table_number == table_number,
        )
        .order_by(RecorderSession.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if recorder_session is None:
        return {"session_id": None, "lines": []}
    path = device_log_path(get_settings().app_persistent_storage, recorder_session.id)
    lines: list[str] = []
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            lines = list(deque(handle, maxlen=tail))
    return {"session_id": recorder_session.id, "lines": [line.rstrip("\n") for line in lines]}
