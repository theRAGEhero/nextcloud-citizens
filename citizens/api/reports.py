"""Organizer report endpoints: JSON structure + Markdown download."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from citizens.db.session import get_db
from citizens.security.identity import CurrentUser
from citizens.services.assemblies import get_owned_assembly
from citizens.services.report import build_report, render_markdown

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


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
    filename = f"{assembly.name[:40].replace(' ', '-')}-report.md"
    return PlainTextResponse(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
