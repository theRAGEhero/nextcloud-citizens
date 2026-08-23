"""Recorder invites: per assembly+table QR tokens (brief §13–§14)."""

import segno
from sqlalchemy import select
from sqlalchemy.orm import Session

from citizens.config import get_settings
from citizens.db.models import Assembly, RecorderInvite
from citizens.db.models.base import utcnow
from citizens.domain import schemas
from citizens.security.recorder_tokens import generate_token, hash_token


def recorder_join_url(token: str) -> str:
    """The URL a table phone opens. The token travels in the fragment so it
    never appears in server access logs; the recorder page exchanges it for a
    short-lived session (Milestone 2)."""
    base = get_settings().nextcloud_url.rstrip("/")
    return f"{base}/index.php/apps/app_api/proxy/citizens/recorder/#/join/{token}"


def generate_invites(session: Session, assembly: Assembly) -> list[schemas.InviteGenerated]:
    """Create fresh invites for every table number, revoking any active ones.

    Raw tokens are returned ONCE here (for the printable QR sheet) and never
    stored — only their SHA-256 hash is persisted.
    """
    table_numbers = sorted(
        {table.number for round_ in assembly.rounds for table in round_.tables}
    ) or list(range(1, assembly.default_table_count + 1))

    now = utcnow()
    for invite in _active_invites(session, assembly.id):
        invite.revoked_at = now

    generated: list[schemas.InviteGenerated] = []
    for number in table_numbers:
        token = generate_token()
        session.add(
            RecorderInvite(assembly_id=assembly.id, table_number=number, token_hash=hash_token(token))
        )
        url = recorder_join_url(token)
        qr = segno.make(url, error="m")
        generated.append(
            schemas.InviteGenerated(
                table_number=number,
                url=url,
                qr_svg=qr.svg_inline(scale=4, dark="#000000"),
            )
        )
    session.flush()
    return generated


def list_invites(session: Session, assembly_id: str) -> list[schemas.InviteOut]:
    invites = session.execute(
        select(RecorderInvite)
        .where(RecorderInvite.assembly_id == assembly_id)
        .order_by(RecorderInvite.table_number, RecorderInvite.created_at)
    ).scalars()
    latest: dict[int, RecorderInvite] = {}
    for invite in invites:
        latest[invite.table_number] = invite
    return [
        schemas.InviteOut(
            id=invite.id,
            table_number=invite.table_number,
            active=invite.revoked_at is None,
            created_at=invite.created_at,
        )
        for invite in latest.values()
    ]


def revoke_invites(session: Session, assembly_id: str) -> int:
    """Revoke all active invites without creating new ones."""
    now = utcnow()
    active = _active_invites(session, assembly_id)
    for invite in active:
        invite.revoked_at = now
    session.flush()
    return len(active)


def find_active_by_token(session: Session, token: str) -> RecorderInvite | None:
    invite = session.execute(
        select(RecorderInvite).where(RecorderInvite.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if invite is None or invite.revoked_at is not None:
        return None
    return invite


def _active_invites(session: Session, assembly_id: str) -> list[RecorderInvite]:
    return list(
        session.execute(
            select(RecorderInvite).where(
                RecorderInvite.assembly_id == assembly_id,
                RecorderInvite.revoked_at.is_(None),
            )
        ).scalars()
    )
