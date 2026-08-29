# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Development/test helpers.

    python -m citizens.devtools seed-recorder-test      one assembly, table-1 invite
    python -m citizens.devtools seed-load-test [N]      one assembly, N tables, N invites

The first is for browser tests. The second backs tests/load/load_g_single_assembly.py:
every table lives in the SAME assembly, which is what a real room looks like and
what calling seed-recorder-test N times does not produce.
"""

import json
import sys

from citizens.config import get_settings
from citizens.db.migrate import run_migrations
from citizens.db.models import Assembly, RecorderInvite, Round, Table
from citizens.db.session import configure_database, session_scope, sqlite_url
from citizens.security.recorder_tokens import generate_token, hash_token
from citizens.storage.paths import db_path, ensure_storage_layout


def seed_recorder_test() -> dict:
    settings = get_settings()
    ensure_storage_layout(settings.app_persistent_storage)
    url = sqlite_url(db_path(settings.app_persistent_storage))
    configure_database(url)
    run_migrations(url)

    with session_scope() as session:
        assembly = Assembly(
            name="TEST Browser Assembly",
            created_by="browser-test",
            expected_participants=10,
            default_table_count=2,
        )
        round_ = Round(position=1, title="TEST Round", question="Browser test?",
                       duration_minutes=30, status="ACTIVE")
        round_.tables = [Table(number=1), Table(number=2)]
        assembly.rounds.append(round_)
        token = generate_token()
        assembly.invites.append(RecorderInvite(table_number=1, token_hash=hash_token(token)))
        session.add(assembly)
        session.flush()
        return {"assembly_id": assembly.id, "round_id": round_.id, "token": token}


def seed_load_test(tables: int = 10) -> dict:
    """One assembly, one round, `tables` tables, one invite each.

    Ten devices in ten assemblies contend for nothing: separate rows, separate
    aggregation, separate everything. Ten devices in ONE assembly is the case a
    venue actually produces, and the only one that puts the writer lock, the
    per-assembly aggregation and the completion burst under simultaneous load.
    """
    settings = get_settings()
    ensure_storage_layout(settings.app_persistent_storage)
    url = sqlite_url(db_path(settings.app_persistent_storage))
    configure_database(url)
    run_migrations(url)

    with session_scope() as session:
        assembly = Assembly(
            name=f"TEST Load {tables} tables",
            created_by="load-test",
            expected_participants=tables * 6,
            default_table_count=tables,
        )
        round_ = Round(position=1, title="TEST Round", question="Load test?",
                       duration_minutes=30, status="ACTIVE")
        round_.tables = [Table(number=n) for n in range(1, tables + 1)]
        assembly.rounds.append(round_)
        seeds = []
        for number in range(1, tables + 1):
            token = generate_token()
            assembly.invites.append(
                RecorderInvite(table_number=number, token_hash=hash_token(token))
            )
            seeds.append({"table_number": number, "token": token})
        session.add(assembly)
        session.flush()
        return {"assembly_id": assembly.id, "round_id": round_.id, "tables": seeds}


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "seed-recorder-test":
        print(json.dumps(seed_recorder_test()))
    elif command == "seed-load-test":
        print(json.dumps(seed_load_test(int(sys.argv[2]) if len(sys.argv) > 2 else 10)))
    else:
        print(
            "Usage: python -m citizens.devtools seed-recorder-test|seed-load-test [N]",
            file=sys.stderr,
        )
        sys.exit(2)
