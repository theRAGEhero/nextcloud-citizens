"""Assembly report: approved findings with evidence references (brief §42)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from citizens.db.models import Assembly, Finding, Participant, Recording, TranscriptSegment

METHODOLOGY_NOTE = (
    "AI was used to assist transcription and analysis. "
    "Findings were reviewed by a human organizer. "
    "“Mentioned at N tables” describes how many discussion tables raised a topic; "
    "it is not a measure of participant support."
)

TYPE_LABELS = {
    "proposal": "Proposals",
    "agreement": "Agreements",
    "disagreement": "Disagreements",
    "concern": "Concerns",
    "question": "Open questions",
    "minority_position": "Minority positions",
    "new_idea": "New ideas",
}

APPROVED = ("APPROVED", "EDITED_AND_APPROVED")


def _timestamp(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def build_report(session: Session, assembly: Assembly, include_drafts: bool = False) -> dict:
    participant_count = session.execute(
        select(func.count()).select_from(Participant).where(Participant.assembly_id == assembly.id)
    ).scalar_one()

    statuses = APPROVED + (("DRAFT",) if include_drafts else ())
    findings = list(
        session.execute(
            select(Finding)
            .where(Finding.assembly_id == assembly.id, Finding.status.in_(statuses))
            .options(selectinload(Finding.evidence))
            .order_by(Finding.created_at)
        ).scalars()
    )
    segment_ids = {
        e.transcript_segment_id for f in findings for e in f.evidence
    }
    segments = {
        s.id: s
        for s in session.execute(
            select(TranscriptSegment).where(TranscriptSegment.id.in_(segment_ids))
        ).scalars()
    } if segment_ids else {}

    recordings_by_round: dict[str, int] = {}
    for recording in session.execute(
        select(Recording).where(Recording.assembly_id == assembly.id)
    ).scalars():
        recordings_by_round[recording.round_id] = recordings_by_round.get(recording.round_id, 0) + 1

    def finding_payload(finding: Finding, table_numbers: dict[str, int]) -> dict:
        return {
            "id": finding.id,
            "type": finding.type,
            "title": finding.title,
            "summary": finding.summary,
            "support": finding.support,
            "status": finding.status,
            "is_draft": finding.status == "DRAFT",
            "table_number": table_numbers.get(finding.table_id or ""),
            "mentioned_table_count": finding.mentioned_table_count,
            "evidence": [
                {
                    "speaker": segments[e.transcript_segment_id].speaker_label,
                    "start": segments[e.transcript_segment_id].start_seconds,
                    "timestamp": _timestamp(segments[e.transcript_segment_id].start_seconds),
                    "text": segments[e.transcript_segment_id].text,
                }
                for e in finding.evidence
                if e.transcript_segment_id in segments
            ],
        }

    rounds_payload = []
    for round_ in assembly.rounds:
        table_numbers = {table.id: table.number for table in round_.tables}
        round_findings = [f for f in findings if f.round_id == round_.id]
        cross = [finding_payload(f, table_numbers) for f in round_findings if f.scope == "round"]
        per_table: dict[int, list[dict]] = {}
        for finding in round_findings:
            if finding.scope != "table":
                continue
            number = table_numbers.get(finding.table_id or "")
            if number is not None:
                per_table.setdefault(number, []).append(finding_payload(finding, table_numbers))
        rounds_payload.append(
            {
                "position": round_.position,
                "title": round_.title,
                "question": round_.question,
                "status": round_.status,
                "recordings": recordings_by_round.get(round_.id, 0),
                "cross_table": cross,
                "tables": [
                    {"table_number": number, "findings": items}
                    for number, items in sorted(per_table.items())
                ],
            }
        )

    return {
        "assembly": {
            "name": assembly.name,
            "description": assembly.description,
            "language": assembly.language,
            "status": assembly.status,
            "participants": participant_count,
            "expected_participants": assembly.expected_participants,
            "tables": assembly.default_table_count,
        },
        "method": (
            "In-person citizens' assembly: participants discussed in small tables; "
            "one phone per table recorded the conversation, which was transcribed "
            "with speaker diarization and analyzed per table, then aggregated across tables."
        ),
        "methodology_note": METHODOLOGY_NOTE,
        "include_drafts": include_drafts,
        "rounds": rounds_payload,
    }


def render_markdown(report: dict) -> str:
    assembly = report["assembly"]
    lines = [
        f"# {assembly['name']} — Assembly Report",
        "",
        assembly["description"] or "",
        "",
        f"- Participants: {assembly['participants']} (expected {assembly['expected_participants']})",
        f"- Tables: {assembly['tables']}",
        f"- Language: {assembly['language'].upper()}",
        "",
        "## Method",
        "",
        report["method"],
        "",
    ]
    for round_ in report["rounds"]:
        lines += [f"## Round {round_['position']} — {round_['title'] or 'Untitled'}", ""]
        if round_["question"]:
            lines += [f"> {round_['question']}", ""]
        if round_["cross_table"]:
            lines += ["### Across all tables", ""]
            for finding in round_["cross_table"]:
                lines += _markdown_finding(finding, cross=True)
        for table in round_["tables"]:
            if not table["findings"]:
                continue
            lines += [f"### Table {table['table_number']}", ""]
            for finding in table["findings"]:
                lines += _markdown_finding(finding, cross=False)
        if not round_["cross_table"] and not any(t["findings"] for t in round_["tables"]):
            lines += ["_No findings for this round yet._", ""]
    lines += ["---", "", f"_{report['methodology_note']}_", ""]
    return "\n".join(lines)


def _markdown_finding(finding: dict, cross: bool) -> list[str]:
    draft = " *(DRAFT — not yet reviewed)*" if finding["is_draft"] else ""
    label = TYPE_LABELS.get(finding["type"], finding["type"])
    header = f"**{label[:-1] if label.endswith('s') else label}: {finding['title']}**{draft}"
    lines = [header, "", finding["summary"], ""]
    if cross and finding["mentioned_table_count"]:
        lines.insert(2, f"Mentioned at {finding['mentioned_table_count']} table(s).")
        lines.insert(3, "")
    for evidence in finding["evidence"][:5]:
        speaker = evidence["speaker"] or "Speaker"
        lines += [f"> [{evidence['timestamp']}] {speaker}: “{evidence['text']}”", ""]
    return lines
