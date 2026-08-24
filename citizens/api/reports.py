"""Organizer report endpoints: JSON structure, Markdown/PDF download, publish."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from citizens.db.models.base import utcnow
from citizens.db.session import get_db
from citizens.security.identity import CurrentUser
from citizens.services.assemblies import get_owned_assembly
from citizens.services.audit import record_audit_event
from citizens.services.branding import logo_path
from citizens.services.report import build_report, render_markdown
from citizens.services.report_pdf import render_pdf

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


def _report_filename(name: str, ext: str) -> str:
    return f"{name[:40].replace(' ', '-')}-report.{ext}"


@router.get("/assemblies/{assembly_id}/report")
def assembly_report(
    assembly_id: str,
    user: CurrentUser,
    session: DB,
    include_drafts: Annotated[bool, Query()] = False,
):
    assembly = get_owned_assembly(session, assembly_id, user)
    return build_report(session, assembly, include_drafts=include_drafts)


@router.get("/assemblies/{assembly_id}/report.md")
def assembly_report_markdown(
    assembly_id: str,
    user: CurrentUser,
    session: DB,
    include_drafts: Annotated[bool, Query()] = False,
):
    assembly = get_owned_assembly(session, assembly_id, user)
    markdown = render_markdown(build_report(session, assembly, include_drafts=include_drafts))
    return PlainTextResponse(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="{_report_filename(assembly.name, "md")}"'
        },
    )


@router.get("/assemblies/{assembly_id}/report.pdf")
def assembly_report_pdf(
    assembly_id: str,
    user: CurrentUser,
    session: DB,
    include_drafts: Annotated[bool, Query()] = False,
):
    assembly = get_owned_assembly(session, assembly_id, user)
    pdf = render_pdf(
        build_report(session, assembly, include_drafts=include_drafts), logo_path()
    )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="{_report_filename(assembly.name, "pdf")}"'
        },
    )


@router.post("/assemblies/{assembly_id}/report/publish")
def publish_report(assembly_id: str, user: CurrentUser, session: DB):
    """Make the report (approved findings + AI summaries) visible on the
    table recorder phones. AI drafts stay organizer-only either way."""
    assembly = get_owned_assembly(session, assembly_id, user)
    assembly.report_published_at = utcnow()
    record_audit_event(session, "report_published", "assembly", assembly.id, actor=user)
    return {"published_at": assembly.report_published_at.isoformat()}


@router.delete("/assemblies/{assembly_id}/report/publish", status_code=204)
def unpublish_report(assembly_id: str, user: CurrentUser, session: DB):
    assembly = get_owned_assembly(session, assembly_id, user)
    assembly.report_published_at = None
    record_audit_event(session, "report_unpublished", "assembly", assembly.id, actor=user)
