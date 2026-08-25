"""Assembly lifecycle: progress, closing, and the frozen final report.

An assembly's report is INTERIM until the organizer closes the session (or,
when every table finished, until they accept the prompt to close). Closing
snapshots the report so that reopening the session — to let a late table
record — can never change what participants already read; a later close (or an
explicit refresh) republishes an updated snapshot.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from citizens.db.models import Assembly, Recording
from citizens.db.models.base import utcnow
from citizens.logging_setup import get_logger
from citizens.services.jobs import enqueue_job
from citizens.services.recording import COMPLETED_STATES, assembly_progress
from citizens.services.report import build_report

log = get_logger(__name__)

__all__ = [
    "assembly_progress",
    "close_assembly",
    "frozen_report",
    "reopen_assembly",
    "snapshot_final_report",
]


def snapshot_final_report(session: Session, assembly: Assembly) -> dict:
    """Freeze the current report as the version participants will read."""
    report = build_report(session, assembly, include_drafts=False)
    assembly.final_report_json = json.dumps(report)
    assembly.final_report_at = utcnow()
    return report


def frozen_report(assembly: Assembly) -> dict | None:
    if not assembly.final_report_json:
        return None
    try:
        return json.loads(assembly.final_report_json)
    except ValueError:
        log.warning("final_report_snapshot_unreadable", assembly_id=assembly.id)
        return None


def close_assembly(session: Session, assembly: Assembly) -> dict:
    """Finish the session: stop recordings, analyze what exists, freeze the
    report. Reversible with reopen_assembly()."""
    for round_ in assembly.rounds:
        if round_.status == "ACTIVE":
            round_.status = "ENDED"
        # a round whose tables recorded but which never got aggregated (e.g.
        # tables that never showed up kept it waiting) gets a final pass
        if not round_.analysis_summary and _round_has_content(session, round_.id):
            enqueue_job(session, "ANALYZE_ROUND", {"round_id": round_.id})
    assembly.closed_at = utcnow()
    assembly.status = "COMPLETE"
    report = snapshot_final_report(session, assembly)
    log.info(
        "assembly_closed",
        assembly_id=assembly.id,
        progress=assembly_progress(session, assembly),
    )
    return report


def reopen_assembly(session: Session, assembly: Assembly) -> None:
    """Accept recordings again. The frozen snapshot stays in place, so phones
    keep showing the report exactly as it was at closing."""
    assembly.closed_at = None
    assembly.status = "ACTIVE"
    log.info("assembly_reopened", assembly_id=assembly.id)


def _round_has_content(session: Session, round_id: str) -> bool:
    return (
        session.execute(
            select(Recording.id).where(
                Recording.round_id == round_id,
                Recording.state.in_(COMPLETED_STATES),
            )
        ).first()
        is not None
    )
