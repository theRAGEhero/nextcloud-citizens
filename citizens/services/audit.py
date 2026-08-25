# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Writing audit events.

Audit rows must be written through the SAME session as the surrounding
operation: SQLite allows a single writer, so opening a second connection
while the request transaction holds the write lock deadlocks against itself.
"""

import json

from sqlalchemy.orm import Session

from citizens.db.models import AuditEvent
from citizens.db.session import session_scope


def record_audit_event(
    session: Session,
    event: str,
    object_type: str | None = None,
    object_id: str | None = None,
    actor: str | None = None,
    data: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            event=event,
            object_type=object_type,
            object_id=object_id,
            actor=actor,
            data_json=json.dumps(data) if data is not None else None,
        )
    )


def record_audit_event_standalone(event: str, **kwargs) -> None:
    """For contexts with no open session (e.g. app lifecycle callbacks)."""
    with session_scope() as session:
        record_audit_event(session, event, **kwargs)
