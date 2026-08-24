"""Durable single-worker job runner (brief §49).

Jobs live in SQLite; the runner polls for due work, executes handlers in a
worker thread (they use sync SQLAlchemy + subprocesses), and applies
exponential backoff on failure. On startup, stale RUNNING jobs (from a crash
or restart) are recovered to RETRY.

CONTRACT: handlers run inside ONE session whose transaction takes SQLite's
single write lock (BEGIN IMMEDIATE). Handlers MUST session.commit() right
before any long external call (ffmpeg, STT/LLM HTTP) — a transaction held
across those starves every API request into 500s after busy_timeout.
"""

import asyncio
import json
from datetime import timedelta

from sqlalchemy import select

from citizens.db.models import AppJob
from citizens.db.models.base import utcnow
from citizens.db.session import session_scope
from citizens.jobs.handlers import HANDLERS, PermanentJobError
from citizens.logging_setup import get_logger

log = get_logger(__name__)

POLL_INTERVAL_SECONDS = 3.0
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 3600


def recover_stale_jobs() -> int:
    with session_scope() as session:
        stale = list(
            session.execute(select(AppJob).where(AppJob.state == "RUNNING")).scalars()
        )
        for job in stale:
            job.state = "RETRY"
            job.locked_at = None
            job.next_attempt_at = utcnow()
        if stale:
            log.warning("jobs_recovered_after_restart", count=len(stale))
        return len(stale)


def _claim_next_job() -> str | None:
    with session_scope() as session:
        job = session.execute(
            select(AppJob)
            .where(AppJob.state.in_(("QUEUED", "RETRY")), AppJob.next_attempt_at <= utcnow())
            .order_by(AppJob.next_attempt_at)
            .limit(1)
        ).scalar_one_or_none()
        if job is None:
            return None
        job.state = "RUNNING"
        job.locked_at = utcnow()
        job.attempts = job.attempts + 1
        return job.id


def _run_job(job_id: str) -> None:
    with session_scope() as session:
        job = session.get(AppJob, job_id)
        if job is None:
            return
        handler = HANDLERS.get(job.type)
        log.info("job_started", job_id=job.id, job_type=job.type, attempt=job.attempts)
        try:
            if handler is None:
                raise PermanentJobError(f"No handler for job type {job.type}")
            handler(session, json.loads(job.payload_json))
        except PermanentJobError as exc:
            job.state = "FAILED"
            job.last_error = str(exc)[:2000]
            job.locked_at = None
            log.error("job_failed_permanently", job_id=job.id, job_type=job.type)
        except Exception as exc:
            session.rollback()
            job = session.get(AppJob, job_id)
            job.last_error = str(exc)[:2000]
            job.locked_at = None
            if job.attempts >= job.max_attempts:
                job.state = "FAILED"
                log.error(
                    "job_failed_max_attempts", job_id=job.id, job_type=job.type, attempts=job.attempts
                )
            else:
                job.state = "RETRY"
                delay = min(BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1)), BACKOFF_MAX_SECONDS)
                job.next_attempt_at = utcnow() + timedelta(seconds=delay)
                log.warning(
                    "job_retry_scheduled", job_id=job.id, job_type=job.type, delay_seconds=delay,
                    exc_info=True,
                )
        else:
            job.state = "SUCCEEDED"
            job.locked_at = None
            log.info("job_succeeded", job_id=job.id, job_type=job.type)


async def run_forever(stop_event: asyncio.Event) -> None:
    recover_stale_jobs()
    while not stop_event.is_set():
        try:
            job_id = await asyncio.to_thread(_claim_next_job)
            if job_id is not None:
                await asyncio.to_thread(_run_job, job_id)
                continue  # look for more work immediately
        except Exception:
            log.error("job_runner_iteration_failed", exc_info=True)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL_SECONDS)
        except TimeoutError:
            pass
