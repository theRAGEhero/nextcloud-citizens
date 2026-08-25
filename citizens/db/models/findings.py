"""AI findings with mandatory evidence links and human review (brief §37–§40)."""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from citizens.db.models.base import Base, TZDateTime, new_uuid, utcnow

FINDING_TYPES = (
    "proposal",
    "agreement",
    "disagreement",
    "concern",
    "question",
    "minority_position",
    "new_idea",
)
FINDING_STATUSES = ("DRAFT", "APPROVED", "REJECTED", "EDITED_AND_APPROVED")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    assembly_id: Mapped[str] = mapped_column(
        ForeignKey("assemblies.id", ondelete="CASCADE"), index=True
    )
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    table_id: Mapped[str | None] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    recording_id: Mapped[str | None] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE")
    )
    scope: Mapped[str] = mapped_column(String(8))  # "table" | "round"
    type: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    support: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    ai_model: Mapped[str] = mapped_column(String(120), default="")
    # verbatim AI output for audit — never mutated by human edits
    original_json: Mapped[str] = mapped_column(Text, default="")
    # round-scope clusters reference the table findings they aggregate
    source_finding_ids: Mapped[str] = mapped_column(Text, default="[]")
    mentioned_table_count: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    reviewed_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    # the quoted evidence vanished with a deleted (or replaced) transcript;
    # reports say so instead of silently showing a finding with no quotes
    evidence_removed_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)

    evidence: Mapped[list["FindingEvidence"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    __table_args__ = (UniqueConstraint("finding_id", "transcript_segment_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )
    transcript_segment_id: Mapped[str] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="CASCADE"), index=True
    )

    finding: Mapped[Finding] = relationship(back_populates="evidence")
