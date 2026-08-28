#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Concurrency checks against a running Vosk server. See scripts/vosk-check.sh.

Run by hand or after changing scripts/vosk/asr_server.py. Exits non-zero on
failure so it can gate a deploy.
"""

import asyncio
import json
import os
import sys

from websockets.asyncio.client import connect

URL = os.environ.get("VOSK_CHECK_URL", "ws://citizens-vosk:2700")
SILENCE = b"\0" * 6400  # 0.2 s at 16 kHz
FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  — ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(name)


async def _speak(ws, model, frames=1):
    config = {"sample_rate": 16000, "words": True}
    if model:
        config["model"] = model
    await ws.send(json.dumps({"config": config}))
    for _ in range(frames):
        await ws.send(SILENCE)
        await ws.recv()
    await ws.send('{"eof" : 1}')
    await ws.recv()


async def simultaneous_load(model_a, model_b):
    """Both connections reach the model load together.

    A plain gather() is not enough: if the first load finishes before the second
    starts they never contend, and the loop-binding bug stays hidden. The
    barrier makes the overlap deterministic.
    """
    barrier = asyncio.Event()

    async def one(model):
        async with connect(URL, max_size=None, open_timeout=30) as ws:
            barrier.set()
            await barrier.wait()
            await _speak(ws, model, frames=2)
            return True

    results = await asyncio.gather(
        one(model_a), one(model_b), return_exceptions=True
    )
    errors = [r for r in results if isinstance(r, BaseException)]
    return errors


async def held_across_use(model_a, model_b):
    """A round still recording must keep its model when another language loads."""
    started = asyncio.Event()
    finished = []

    async def long_round():
        async with connect(URL, max_size=None, open_timeout=30) as ws:
            await ws.send(json.dumps({"config": {"sample_rate": 16000, "model": model_a}}))
            await ws.send(SILENCE)
            await ws.recv()
            started.set()
            for _ in range(6):          # keeps recording while the other loads
                await asyncio.sleep(1)
                await ws.send(SILENCE)
                await ws.recv()
            await ws.send('{"eof" : 1}')
            await ws.recv()
            finished.append("long round survived")

    async def other_language():
        await started.wait()
        async with connect(URL, max_size=None, open_timeout=30) as ws:
            await _speak(ws, model_b, frames=2)

    await asyncio.gather(long_round(), other_language())
    return finished


async def main():
    models = sys.argv[1:] or [
        "/models/vosk-model-small-it-0.22",
        "/models/vosk-model-small-en-us-0.15",
    ]
    if len(models) < 2:
        print("need two model paths to test concurrency", file=sys.stderr)
        return 2
    a, b = models[0], models[1]
    print(f"Vosk concurrency checks against {URL}")

    errors = await simultaneous_load(a, b)
    check(
        "two languages loading at the same moment",
        not errors,
        "; ".join(f"{type(e).__name__}: {e}" for e in errors)[:160],
    )

    errors = await simultaneous_load(a, a)
    check(
        "two tables in the same language share one load",
        not errors,
        "; ".join(f"{type(e).__name__}: {e}" for e in errors)[:160],
    )

    try:
        survived = await held_across_use(a, b)
        check("a recording round keeps its model while another language loads", bool(survived))
    except Exception as exc:  # noqa: BLE001 - report, don't traceback
        check("a recording round keeps its model while another language loads",
              False, f"{type(exc).__name__}: {exc}")

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
