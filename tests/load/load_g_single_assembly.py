# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test G: 10 table devices in ONE assembly, the way a real room is shaped.

load_f_concurrent_devices.py runs 10 devices across 10 *separate* assemblies,
so they contend for nothing — separate rows, separate aggregation, separate
everything. That is why the join-limiter bug (keyed on IP, so table 11 at a
venue was refused) and the writer-lock stalls went unseen by it for so long.

This one puts every device in the same assembly and, at each phase, releases
them through a barrier so the requests genuinely overlap rather than queueing
politely behind each other. It reports the slowest request per phase, because
under SQLite's single writer that is where a regression shows up first — a
failure count of zero with a 9-second worst case is still a broken room.

NOT a pytest test: it needs the throwaway instance from
scripts/browser-test-env.sh already running on :23100, and ffmpeg on the host.
Never point it at the live instance — it creates junk assemblies and real load.

    scripts/browser-test-env.sh start
    python3 tests/load/load_g_single_assembly.py [tables]
"""

import concurrent.futures
import hashlib
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:23100"
REPO = "/root/NextCloud-Citizen"
CHUNKS = 5

# every phase's request latencies, so one slow outlier cannot hide in a mean
TIMINGS: dict[str, list[float]] = {}
FAILURES: list[str] = []
_LOCK = threading.Lock()


def api(method, path, data=None, token=None, raw=None, sha=None, phase=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if raw is not None:
        headers["Content-Type"] = "application/octet-stream"
        headers["X-Chunk-SHA256"] = sha
        body = raw
    elif data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    else:
        body = None
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
    started = time.monotonic()
    try:
        result = json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as exc:
        with _LOCK:
            FAILURES.append(f"{method} {path} -> {exc.code} {exc.read()[:200]!r}")
        raise
    finally:
        if phase:
            with _LOCK:
                TIMINGS.setdefault(phase, []).append(time.monotonic() - started)
    return result


def wait(barrier):
    """Barrier that gives up rather than hanging the run.

    A plain Barrier deadlocks the survivors when one thread dies mid-phase, so
    a single 500 turned a 60-second test into a 600-second hang that said
    nothing about the app. Aborting propagates the break to everyone instead.
    """
    try:
        barrier.wait(timeout=90)
    except threading.BrokenBarrierError:
        raise
    except Exception:
        barrier.abort()
        raise


def device(seed, round_id, chunks, barrier):
    """One table phone, held at a barrier before each phase so all N overlap."""
    wait(barrier)
    token = api("POST", "/api/v1/public/join", {"token": seed["token"]}, phase="join")[
        "session_token"
    ]

    wait(barrier)
    recording = api(
        "POST",
        "/api/v1/public/recorder/start",
        {"round_id": round_id, "mime_type": "audio/webm"},
        token=token,
        phase="start",
    )["recording_id"]

    for seq, blob in enumerate(chunks):
        wait(barrier)
        api(
            "POST",
            f"/api/v1/public/recorder/recordings/{recording}/chunks/{seq}",
            token=token,
            raw=blob,
            sha=hashlib.sha256(blob).hexdigest(),
            phase="chunk",
        )
        api(
            "POST",
            "/api/v1/public/recorder/heartbeat",
            {"recording_active": True, "local_chunks": seq + 1,
             "acked_chunks": seq + 1, "storage_ok": True},
            token=token,
            phase="heartbeat",
        )

    # the burst that matters: every table stops talking when the facilitator
    # calls time, so all N completions land within the same second
    wait(barrier)
    result = api(
        "POST",
        f"/api/v1/public/recorder/recordings/{recording}/complete",
        {"total_chunks": len(chunks)},
        token=token,
        phase="complete",
    )
    if result["missing_sequences"]:
        with _LOCK:
            FAILURES.append(f"table {seed['table_number']}: missing {result['missing_sequences']}")

    for _ in range(120):
        status = api("GET", f"/api/v1/public/recorder/recordings/{recording}", token=token)
        if status["state"] in ("AUDIO_READY", "AUDIO_INVALID"):
            return status
        time.sleep(1)
    return status


def main():
    tables = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    seed = json.loads(
        subprocess.run(
            ["sh", f"{REPO}/scripts/browser-test-env.sh", "seed-load", str(tables)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )
    audio = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:a", "libopus", "-b:a", "24k", "-f", "webm", "pipe:1"],
        capture_output=True, check=True,
    ).stdout
    size = len(audio) // CHUNKS + 1
    chunks = [c for i in range(CHUNKS) if (c := audio[i * size:(i + 1) * size])]

    barrier = threading.Barrier(tables)
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=tables) as pool:
        futures = [
            pool.submit(device, table, seed["round_id"], chunks, barrier)
            for table in seed["tables"]
        ]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as exc:  # already recorded in FAILURES
                results.append({"state": f"EXCEPTION {type(exc).__name__}"})
    elapsed = time.time() - started

    states = [r["state"] for r in results]
    print(f"\nassembly={seed['assembly_id']} tables={tables} elapsed={elapsed:.1f}s")
    print(f"states={dict((s, states.count(s)) for s in set(states))}")
    for phase, values in TIMINGS.items():
        values.sort()
        p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
        print(f"  {phase:<10} n={len(values):<4} median={values[len(values)//2]*1000:6.0f}ms "
              f"p95={p95*1000:6.0f}ms max={values[-1]*1000:6.0f}ms")
    for failure in FAILURES[:10]:
        print(f"  FAIL {failure}")
    ok = not FAILURES and all(s == "AUDIO_READY" for s in states)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
