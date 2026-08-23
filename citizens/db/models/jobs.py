"""Durable background jobs persisted in SQLite (brief §49)."""

from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from citizens.db.models.base import Base, TZDateTime, new_uuid, utcnow

JOB_STATES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "RETRY")


class AppJob(Base):
    __tablename__ = "app_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    type: Mapped[str] = mapped_column(String(40), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    state: Mapped[str] = mapped_column(String(12), default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)
