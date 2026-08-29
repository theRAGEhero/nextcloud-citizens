# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Async route handlers must not do blocking work on the event loop.

FastAPI runs `def` handlers in a threadpool but `async def` handlers directly
on the event loop. A blocking call in one of those does not slow that request —
it freezes the whole server, because nothing else can run until it returns.

This is not hypothetical. `upload_chunk` is the app's only async handler, and it
called SQLite (which waits up to busy_timeout for the writer slot), wrote the
chunk to disk, and read provider config (an OCS call to Nextcloud whenever the
30-second cache expired) inline. With ten tables uploading at once a plain
redirect that touches no database took 27 seconds and then timed out, and
commits — which the loop has to schedule — stalled until waiting writers gave up
with "database is locked". tests/load/load_g_single_assembly.py reproduces it.

The blocking work belongs in a nested function handed to run_in_threadpool, so
this walks only the coroutine's own body and skips nested definitions.
"""

import ast
import pathlib

API_DIR = pathlib.Path(__file__).resolve().parents[2] / "citizens" / "api"

# Calls that block: the database, the filesystem, and config reads that can
# make a network call to Nextcloud.
BLOCKING_NAMES = {
    "live_stt_snapshot",
    "data_handling_summary",
    "_session_from_authorization",
    "receive_chunk",
    "complete_recording",
    "get_session_recording",
}
# Anything reached through the SQLAlchemy session or the recording service.
BLOCKING_RECEIVERS = {"session", "rec_svc"}


def _called_name(node: ast.Call) -> tuple[str, str]:
    """(receiver, attribute) for a call, with empty strings where absent."""
    func = node.func
    if isinstance(func, ast.Attribute):
        receiver = func.value.id if isinstance(func.value, ast.Name) else ""
        return receiver, func.attr
    if isinstance(func, ast.Name):
        return "", func.id
    return "", ""


def _direct_body(node: ast.AsyncFunctionDef) -> list[ast.AST]:
    """Every node in the coroutine except those inside a nested definition."""
    nested = {
        inner
        for child in ast.walk(node)
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        and child is not node
        for inner in ast.walk(child)
    }
    return [child for child in ast.walk(node) if child not in nested]


def test_async_handlers_do_no_blocking_work_inline():
    offenders = []
    for path in sorted(API_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for child in _direct_body(node):
                if not isinstance(child, ast.Call):
                    continue
                receiver, attribute = _called_name(child)
                if attribute in BLOCKING_NAMES or receiver in BLOCKING_RECEIVERS:
                    offenders.append(
                        f"{path.name}:{child.lineno} {node.name}() calls "
                        f"{receiver + '.' if receiver else ''}{attribute} on the event loop"
                    )
    assert not offenders, (
        "blocking call in an async handler — wrap it in a nested function and "
        "await run_in_threadpool(...):\n  " + "\n  ".join(offenders)
    )
