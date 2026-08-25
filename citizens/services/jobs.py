# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Enqueueing durable jobs (runner lives in citizens/jobs/)."""

import json

from sqlalchemy.orm import Session

from citizens.db.models import AppJob


def enqueue_job(session: Session, job_type: str, payload: dict, max_attempts: int = 5) -> AppJob:
    job = AppJob(type=job_type, payload_json=json.dumps(payload), max_attempts=max_attempts)
    session.add(job)
    session.flush()
    return job
