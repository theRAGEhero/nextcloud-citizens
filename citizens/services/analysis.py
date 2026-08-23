"""AI analysis: per-table structured extraction and cross-table clustering
(brief §36–§39). Every table finding must cite real transcript segments;
anything without valid evidence is dropped, never stored.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from citizens.db.models import (
    Assembly,
    Finding,
    FindingEvidence,
    Recording,
    Round,
    Transcript,
    TranscriptSegment,
)
from citizens.domain.analysis_schemas import RoundAnalysis, TableAnalysis
from citizens.logging_setup import get_logger
from citizens.providers.analysis.openai_compat import AnalysisError, chat_json
from citizens.services import provider_config

log = get_logger(__name__)

COALESCE_GAP_SECONDS = 1.5

LANGUAGE_NAMES = {"en": "English", "it": "Italian", "de": "German", "fr": "French", "es": "Spanish"}


def analysis_ready(store: provider_config.ConfigStore) -> bool:
    return (
        provider_config.get_setting(store, "analysis_enabled") == "1"
        and bool(store.get_value("analysis_api_key"))
    )


def coalesce_segments(segments: list[TranscriptSegment]) -> list[dict]:
    """Merge consecutive same-speaker fragments into readable blocks. Each
    block keeps every member segment id so evidence citations stay valid."""
    blocks: list[dict] = []
    for segment in segments:
        last = blocks[-1] if blocks else None
        if (
            last is not None
            and last["speaker"] == segment.speaker_label
            and segment.start_seconds - last["end"] <= COALESCE_GAP_SECONDS
        ):
            last["ids"].append(segment.id)
            last["end"] = segment.end_seconds
            last["text"] = f"{last['text']} {segment.text}".strip()
        else:
            blocks.append(
                {
                    "ids": [segment.id],
                    "speaker": segment.speaker_label,
                    "start": segment.start_seconds,
                    "end": segment.end_seconds,
                    "text": segment.text,
                }
            )
    return blocks


def _timestamp(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def _analysis_config(store: provider_config.ConfigStore) -> tuple[str, str, str]:
    key = store.get_value("analysis_api_key")
    if not key:
        raise AnalysisError("No analysis API key configured", permanent=True)
    return (
        provider_config.get_setting(store, "analysis_base_url"),
        key,
        provider_config.get_setting(store, "analysis_model"),
    )


TABLE_SYSTEM = """You are an analyst supporting an in-person citizens' assembly.
You analyze ONE table's discussion transcript.

Rules:
- Respond with ONLY a JSON object: {{"summary": "...", "findings": [{{"type": ...,
  "title": ..., "summary": ..., "support": ..., "evidence_segment_ids": [...]}}]}}
- "summary" (top level) is ALWAYS required: a neutral 2-4 sentence description
  of what the table actually discussed — even if it was small talk or off the
  round question. Never leave it out.
- "type" is one of: proposal, agreement, disagreement, concern, question,
  minority_position, new_idea.
- "support" (optional) is one of: strong, mixed, weak, unclear.
- EVERY finding MUST cite at least one evidence_segment_ids value copied
  EXACTLY from the segment ids in the transcript. Never invent ids.
- Only report what participants actually said. Do not invent content.
- If the discussion contains nothing substantive for the round question,
  return {{"summary": "...", "findings": []}}.
- Write everything in {language}."""

ROUND_SYSTEM = """You are an analyst supporting an in-person citizens' assembly.
You aggregate findings from multiple discussion tables of the SAME round into
cross-table clusters (recurring proposals, shared concerns, disagreements,
minority positions, questions, unique new ideas).

Rules:
- Respond with ONLY a JSON object: {{"summary": "...", "clusters": [{{"type": ...,
  "title": ..., "summary": ..., "source_finding_ids": [...]}}]}}
- "summary" (top level) is ALWAYS required: a neutral 2-4 sentence overview of
  the round across all tables.
- "type" is one of: proposal, agreement, disagreement, concern, question,
  minority_position, new_idea.
- EVERY cluster MUST list source_finding_ids copied EXACTLY from the finding
  ids provided. Never invent ids.
- Never state or imply percentages of participant support; tables are not
  votes.
- Write everything in {language}."""


def analyze_table(session: Session, store: provider_config.ConfigStore, recording: Recording) -> int:
    """Extract findings for one table recording; returns stored finding count."""
    transcript = session.execute(
        select(Transcript).where(Transcript.recording_id == recording.id)
    ).scalar_one_or_none()
    if transcript is None:
        raise AnalysisError("No transcript for this recording", permanent=True)

    _delete_existing(session, recording_id=recording.id, scope="table", only_drafts=True)

    if not transcript.segments:
        recording.analysis_summary = "No speech was detected in this recording."
        log.info("analysis_empty_transcript", recording_id=recording.id)
        return 0

    assembly = session.get(Assembly, recording.assembly_id)
    round_ = session.get(Round, recording.round_id)
    language = LANGUAGE_NAMES.get(assembly.language if assembly else "en", "English")
    valid_ids = {segment.id for segment in transcript.segments}

    lines = [
        f"[{'|'.join(block['ids'])}] {block['speaker'] or 'SPEAKER'} "
        f"({_timestamp(block['start'])}-{_timestamp(block['end'])}): {block['text']}"
        for block in coalesce_segments(list(transcript.segments))
    ]
    user_prompt = (
        f"Assembly: {assembly.name if assembly else ''}\n"
        f"Round question: {round_.question or round_.title if round_ else ''}\n"
        f"Table number: {recording.table_number}\n\n"
        "Transcript segments (format: [segment ids] SPEAKER (start-end): text):\n"
        + "\n".join(lines)
    )

    base_url, key, model = _analysis_config(store)
    log.info("analysis_started", recording_id=recording.id, scope="table", segments=len(lines))
    result = chat_json(
        base_url, key, model, TABLE_SYSTEM.format(language=language), user_prompt, TableAnalysis
    )
    recording.analysis_summary = result.summary

    stored = 0
    dropped = 0
    for item in result.findings:
        evidence_ids = {
            eid for raw in item.evidence_segment_ids for eid in raw.split("|") if eid in valid_ids
        }
        if not evidence_ids:
            dropped += 1
            continue  # a finding without real evidence is INVALID (brief §38)
        finding = Finding(
            assembly_id=recording.assembly_id,
            round_id=recording.round_id,
            table_id=recording.table_id,
            recording_id=recording.id,
            scope="table",
            type=item.type,
            title=item.title,
            summary=item.summary,
            support=item.support or "",
            ai_model=model,
            original_json=item.model_dump_json(),
        )
        for segment_id in sorted(evidence_ids):
            finding.evidence.append(FindingEvidence(transcript_segment_id=segment_id))
        session.add(finding)
        stored += 1
    session.flush()
    log.info(
        "analysis_completed", recording_id=recording.id, scope="table",
        findings=stored, dropped_without_evidence=dropped,
    )
    return stored


def analyze_round(session: Session, store: provider_config.ConfigStore, round_: Round) -> int:
    """Cluster all table findings of a round into cross-table findings."""
    table_findings = list(
        session.execute(
            select(Finding).where(
                Finding.round_id == round_.id,
                Finding.scope == "table",
                Finding.status != "REJECTED",
            )
        ).scalars()
    )
    _delete_existing(session, round_id=round_.id, scope="round", only_drafts=True)
    if not table_findings:
        summaries = [
            f"Table {rec.table_number}: {rec.analysis_summary}"
            for rec in session.execute(
                select(Recording).where(
                    Recording.round_id == round_.id, Recording.analysis_summary != ""
                )
            ).scalars()
        ]
        round_.analysis_summary = (
            " ".join(summaries)[:1500]
            if summaries
            else "No substantive findings emerged from this round's discussions."
        )
        log.info("analysis_round_no_findings", round_id=round_.id)
        return 0

    assembly = session.get(Assembly, round_.assembly_id)
    language = LANGUAGE_NAMES.get(assembly.language if assembly else "en", "English")
    tables_by_finding: dict[str, str | None] = {f.id: f.table_id for f in table_findings}
    total_tables = len({f.table_id for f in table_findings if f.table_id})
    table_numbers = _table_numbers(session, round_)

    lines = [
        f"[{f.id}] table {table_numbers.get(f.table_id or '', '?')} · {f.type} · {f.title}: {f.summary[:400]}"
        for f in table_findings
    ]
    user_prompt = (
        f"Assembly: {assembly.name if assembly else ''}\n"
        f"Round question: {round_.question or round_.title}\n"
        f"Tables that produced findings: {total_tables}\n\n"
        "Table findings (format: [finding id] table N · type · title: summary):\n"
        + "\n".join(lines)
    )

    base_url, key, model = _analysis_config(store)
    log.info("analysis_started", round_id=round_.id, scope="round", source_findings=len(lines))
    result = chat_json(
        base_url, key, model, ROUND_SYSTEM.format(language=language), user_prompt, RoundAnalysis
    )
    round_.analysis_summary = result.summary

    stored = 0
    for cluster in result.clusters:
        source_ids = [fid for fid in cluster.source_finding_ids if fid in tables_by_finding]
        if not source_ids:
            continue
        # table count computed from real links, never trusted from the model
        mentioned = len({tables_by_finding[fid] for fid in source_ids if tables_by_finding[fid]})
        session.add(
            Finding(
                assembly_id=round_.assembly_id,
                round_id=round_.id,
                scope="round",
                type=cluster.type,
                title=cluster.title,
                summary=cluster.summary,
                ai_model=model,
                original_json=cluster.model_dump_json(),
                source_finding_ids=json.dumps(source_ids),
                mentioned_table_count=mentioned,
            )
        )
        stored += 1
    session.flush()
    log.info("analysis_completed", round_id=round_.id, scope="round", findings=stored)
    return stored


def _table_numbers(session: Session, round_: Round) -> dict[str, int]:
    return {table.id: table.number for table in round_.tables}


def _delete_existing(
    session: Session,
    scope: str,
    recording_id: str | None = None,
    round_id: str | None = None,
    only_drafts: bool = True,
) -> None:
    query = select(Finding).where(Finding.scope == scope)
    if recording_id:
        query = query.where(Finding.recording_id == recording_id)
    if round_id:
        query = query.where(Finding.round_id == round_id)
    if only_drafts:
        query = query.where(Finding.status == "DRAFT")
    for finding in session.execute(query).scalars():
        session.delete(finding)
    session.flush()
