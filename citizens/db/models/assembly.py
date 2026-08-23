"""Assembly-core entities (brief §45–§46)."""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from citizens.db.models.base import Base, TZDateTime, new_uuid, utcnow

ASSEMBLY_STATUSES = ("DRAFT", "READY", "ACTIVE", "PROCESSING", "REVIEW", "COMPLETE")
ROUND_STATUSES = ("NOT_STARTED", "ACTIVE", "ENDED", "PROCESSING", "READY_FOR_REVIEW")


class Assembly(Base):
    __tablename__ = "assemblies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(10), default="en")
    scheduled_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    expected_participants: Mapped[int] = mapped_column(Integer, default=0)
    default_table_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)

    rounds: Mapped[list["Round"]] = relationship(
        back_populates="assembly", cascade="all, delete-orphan", order_by="Round.position"
    )
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="assembly", cascade="all, delete-orphan", order_by="Participant.label"
    )
    invites: Mapped[list["RecorderInvite"]] = relationship(
        back_populates="assembly", cascade="all, delete-orphan"
    )


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    assembly_id: Mapped[str] = mapped_column(
        ForeignKey("assemblies.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default="NOT_STARTED")
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    ended_at: Mapped[datetime | None] = mapped_column(TZDateTime())

    assembly: Mapped[Assembly] = relationship(back_populates="rounds")
    tables: Mapped[list["Table"]] = relationship(
        back_populates="round", cascade="all, delete-orphan", order_by="Table.number"
    )


class Table(Base):
    __tablename__ = "tables"
    __table_args__ = (UniqueConstraint("round_id", "number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default="IDLE")

    round: Mapped[Round] = relationship(back_populates="tables")
    assignments: Mapped[list["TableAssignment"]] = relationship(
        back_populates="table", cascade="all, delete-orphan"
    )


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("assembly_id", "label"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    assembly_id: Mapped[str] = mapped_column(
        ForeignKey("assemblies.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)

    assembly: Mapped[Assembly] = relationship(back_populates="participants")


class TableAssignment(Base):
    __tablename__ = "table_assignments"
    # one table per participant per round
    __table_args__ = (UniqueConstraint("round_id", "participant_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True
    )

    table: Mapped[Table] = relationship(back_populates="assignments")
    participant: Mapped[Participant] = relationship()


class RecorderInvite(Base):
    __tablename__ = "recorder_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    assembly_id: Mapped[str] = mapped_column(
        ForeignKey("assemblies.id", ondelete="CASCADE"), index=True
    )
    table_number: Mapped[int] = mapped_column(Integer)
    # only the SHA-256 hex digest of the invite token is ever stored
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    last_used_at: Mapped[datetime | None] = mapped_column(TZDateTime())

    assembly: Mapped[Assembly] = relationship(back_populates="invites")
