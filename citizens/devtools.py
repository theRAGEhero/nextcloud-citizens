"""Development/test helpers. Usage: python -m citizens.devtools seed-recorder-test

Creates a TEST assembly with one round and two tables, generates a table-1
invite, and prints JSON with the raw invite token — for browser tests only.
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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "seed-recorder-test":
        print(json.dumps(seed_recorder_test()))
    else:
        print("Usage: python -m citizens.devtools seed-recorder-test", file=sys.stderr)
        sys.exit(2)
