"""Organizer API for recorder invites/QR codes. Public recorder routes come in Milestone 2."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from citizens.db.session import get_db
from citizens.domain import schemas
from citizens.security.identity import CurrentUser
from citizens.services import invites as invite_svc
from citizens.services.assemblies import get_owned_assembly
from citizens.services.audit import record_audit_event

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


@router.get("/assemblies/{assembly_id}/invites", response_model=list[schemas.InviteOut])
def list_invites(assembly_id: str, user: CurrentUser, session: DB):
    get_owned_assembly(session, assembly_id, user)
    return invite_svc.list_invites(session, assembly_id)


@router.post(
    "/assemblies/{assembly_id}/invites/generate",
    response_model=list[schemas.InviteGenerated],
    status_code=201,
)
def generate_invites(assembly_id: str, user: CurrentUser, session: DB):
    """Returns raw invite URLs + QR SVGs exactly once; only hashes are stored.
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
