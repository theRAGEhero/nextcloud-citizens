"""Milestone 2 recorder pipeline: join → record → chunk upload → assemble.

Uses real opus/webm audio generated with ffmpeg and the real assembly
pipeline (concat + ffprobe + remux), exercising duplicate-upload (brief
Test D) and missing-chunk (Test E) behaviour.
"""

import hashlib
import re
import subprocess
import time

import pytest


def _make_webm_audio(tmp_path, seconds: float = 3.0) -> bytes:
    path = tmp_path / "source.webm"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:a", "libopus", "-b:a", "32k", str(path),
        ],
        check=True,
        timeout=120,
    )
    return path.read_bytes()


def _split(data: bytes, parts: int) -> list[bytes]:
    size = len(data) // parts + 1
    return [data[i * size : (i + 1) * size] for i in range(parts) if data[i * size : (i + 1) * size]]


@pytest.fixture
def recorder(client):
    """An assembly with invites, joined as the table-1 recorder."""
    assembly = client.post(
        "/api/v1/assemblies",
        json={
            "name": "TEST Recorder",
            "default_table_count": 2,
            "rounds": [{"title": "R1", "question": "Q?", "duration_minutes": 30}],
        },
    ).json()
    client.post(f"/api/v1/rounds/{assembly['rounds'][0]['id']}/start")
    invites = client.post(f"/api/v1/assemblies/{assembly['id']}/invites/generate").json()
    token = re.search(r"#/join/(.+)$", invites[0]["url"]).group(1)
    joined = client.post(
        "/api/v1/public/join", json={"token": token}, headers={"X-Forwarded-For": "10.1.1.1"}
    )
    assert joined.status_code == 200, joined.text
    data = joined.json()
    return {
        "client": client,
        "assembly": assembly,
        "headers": {"Authorization": f"Bearer {data['session_token']}"},
        "round_id": data["rounds"][0]["id"],
    }


def _upload(recorder, recording_id: str, sequence: int, blob: bytes, sha=None):
    return recorder["client"].post(
        f"/api/v1/public/recorder/recordings/{recording_id}/chunks/{sequence}",
        content=blob,
        headers={
            **recorder["headers"],
            "Content-Type": "application/octet-stream",
            "X-Chunk-SHA256": sha or hashlib.sha256(blob).hexdigest(),
        },
    )


def _start(recorder) -> str:
    response = recorder["client"].post(
        "/api/v1/public/recorder/start",
        json={"round_id": recorder["round_id"], "mime_type": "audio/webm;codecs=opus"},
        headers=recorder["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()["recording_id"]


def _wait_for_state(recorder, recording_id: str, target: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    status = {}
    while time.time() < deadline:
        status = (
            recorder["client"]
            .get(f"/api/v1/public/recorder/recordings/{recording_id}", headers=recorder["headers"])
            .json()
        )
        if status["state"] in (target, "AUDIO_INVALID"):
            return status
        time.sleep(0.5)
    return status


def test_full_recording_pipeline(recorder, tmp_path, settings_env):
    audio = _make_webm_audio(tmp_path)
    chunks = _split(audio, 4)
    recording_id = _start(recorder)

    for sequence, blob in enumerate(chunks):
        response = _upload(recorder, recording_id, sequence, blob)
        assert response.status_code == 200, response.text
        assert response.json() == {
            "acknowledged": True, "duplicate": False, "sequence_number": sequence,
        }

    done = recorder["client"].post(
        f"/api/v1/public/recorder/recordings/{recording_id}/complete",
        json={"total_chunks": len(chunks)},
        headers=recorder["headers"],
    )
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "ASSEMBLING"

    status = _wait_for_state(recorder, recording_id, "AUDIO_READY")
    assert status["state"] == "AUDIO_READY", status
    assert status["duration_seconds"] == pytest.approx(3.0, abs=0.5)

    # canonical file exists and is valid audio
    assembled = list((settings_env.app_persistent_storage / "assembled").rglob("*.webm"))
    assert len(assembled) == 1
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(assembled[0])],
        capture_output=True, text=True, check=True,
    )
    assert float(probe.stdout.strip()) == pytest.approx(3.0, abs=0.5)


def test_duplicate_chunk_is_idempotent(recorder, tmp_path):
    """Brief §56 Test D."""
    audio = _make_webm_audio(tmp_path, seconds=1.0)
    chunks = _split(audio, 2)
    recording_id = _start(recorder)

    assert _upload(recorder, recording_id, 0, chunks[0]).json()["duplicate"] is False
    duplicate = _upload(recorder, recording_id, 0, chunks[0])
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    # same sequence with DIFFERENT bytes must be rejected
    conflict = _upload(recorder, recording_id, 0, chunks[1])
    assert conflict.status_code == 409

    status = recorder["client"].get(
        f"/api/v1/public/recorder/recordings/{recording_id}", headers=recorder["headers"]
    ).json()
    assert status["received_chunks"] == 1


def test_missing_chunk_detected_and_recoverable(recorder, tmp_path):
    """Brief §56 Test E: server refuses to assemble with a gap."""
    audio = _make_webm_audio(tmp_path, seconds=2.0)
    chunks = _split(audio, 4)
    recording_id = _start(recorder)

    for sequence in (0, 1, 3):
        assert _upload(recorder, recording_id, sequence, chunks[sequence]).status_code == 200

    done = recorder["client"].post(
        f"/api/v1/public/recorder/recordings/{recording_id}/complete",
        json={"total_chunks": 4},
        headers=recorder["headers"],
    ).json()
    assert done["state"] == "WAITING_FOR_CHUNKS"
    assert done["missing_sequences"] == [2]

    # resend the gap, complete again
    assert _upload(recorder, recording_id, 2, chunks[2]).status_code == 200
    done = recorder["client"].post(
        f"/api/v1/public/recorder/recordings/{recording_id}/complete",
        json={"total_chunks": 4},
        headers=recorder["headers"],
    ).json()
    assert done["state"] == "ASSEMBLING"
    assert _wait_for_state(recorder, recording_id, "AUDIO_READY")["state"] == "AUDIO_READY"


def test_checksum_mismatch_rejected(recorder):
    recording_id = _start(recorder)
    response = _upload(recorder, recording_id, 0, b"real-bytes", sha="0" * 64)
    assert response.status_code == 400
    assert "hecksum" in response.json()["detail"]


def test_recorder_auth_rules(recorder):
    client = recorder["client"]
    # no bearer
    assert client.get("/api/v1/public/recorder/status").status_code == 401
    # garbage bearer
    assert (
        client.get(
            "/api/v1/public/recorder/status", headers={"Authorization": "Bearer nonsense"}
        ).status_code
        == 401
    )
    # invalid invite token
    assert (
        client.post(
            "/api/v1/public/join", json={"token": "x" * 43}, headers={"X-Forwarded-For": "10.9.9.9"}
        ).status_code
        == 401
    )


def test_join_rate_limited(client):
    headers = {"X-Forwarded-For": "10.7.7.7"}
    for _ in range(10):
        client.post("/api/v1/public/join", json={"token": "y" * 43}, headers=headers)
    throttled = client.post("/api/v1/public/join", json={"token": "y" * 43}, headers=headers)
    assert throttled.status_code == 429
