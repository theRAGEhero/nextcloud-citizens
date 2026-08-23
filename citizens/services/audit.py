"""Writing audit events."""

import json

from citizens.db.models import AuditEvent
from citizens.db.session import session_scope


def record_audit_event(
    event: str,
    object_type: str | None = None,
    object_id: str | None = None,
    actor: str | None = None,
    data: dict | None = None,
) -> None:
    with session_scope() as session:
        session.add(
            AuditEvent(
                event=event,
                object_type=object_type,
                object_id=object_id,
                actor=actor,
                data_json=json.dumps(data) if data is not None else None,
            )
        )
