"""Independent mode: report auto-availability when every table completes,
and per-table summaries in the public status payload."""

import hashlib
import re
import subprocess
import time


def _make_webm_audio(tmp_path) -> bytes:
    path = tmp_path / "indep.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=2",
         "-c:a", "libopus", "-b:a", "32k", str(path)],
        check=True,
        timeout=120,
    )
    return path.read_bytes()


def _record_round(client, headers, round_id, audio):
    started = client.post(
        "/api/v1/public/recorder/start",
        json={"round_id": round_id, "mime_type": "audio/webm"},
        headers=headers,
    )
    assert started.status_code == 201, started.text
    recording_id = started.json()["recording_id"]
    upload = client.post(
        f"/api/v1/public/recorder/recordings/{recording_id}/chunks/0",
        content=audio,
        headers={**headers, "Content-Type": "application/octet-stream",
                 "X-Chunk-SHA256": hashlib.sha256(audio).hexdigest()},
    )
    assert upload.status_code == 200, upload.text
    done = client.post(
        f"/api/v1/public/recorder/recordings/{recording_id}/complete",
        json={"total_chunks": 1},
        headers=headers,
    )
    assert done.json()["missing_sequences"] == []
    return recording_id


def _wait_report_available(client, headers, timeout=30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get("/api/v1/public/recorder/status", headers=headers).json()
        if status["report_available"]:
            return True
        time.sleep(0.5)
    return False


def _join_table1(client, assembly):
    token = re.search(r"#/join/(.+)$", assembly["invites"][0]["url"]).group(1)
    joined = client.post(
        "/api/v1/public/join", json={"token": token}, headers={"X-Forwarded-For": "10.7.7.1"}
    ).json()
    return {"Authorization": f"Bearer {joined['session_token']}"}, joined


def test_independent_report_auto_available_when_complete(client, tmp_path, monkeypatch):
    from citizens.services import provider_config

    # analysis is off in this deployment: completion = every table recorded
    monkeypatch.setattr(provider_config, "analysis_enabled_cached", lambda: False)

    assembly = client.post(
        "/api/v1/assemblies",
        json={"name": "TEST Indep Auto", "recording_mode": "independent",
              "default_table_count": 1,
              "rounds": [{"title": "R1", "question": "Q1", "duration_minutes": 10},
                         {"title": "R2", "question": "Q2", "duration_minutes": 10}]},
    ).json()
    headers, joined = _join_table1(client, assembly)
    audio = _make_webm_audio(tmp_path)

    # after round 1 only: not yet complete → no report
    _record_round(client, headers, joined["rounds"][0]["id"], audio)
    status = client.get("/api/v1/public/recorder/status", headers=headers).json()
    assert status["report_available"] is False
    assert client.get("/api/v1/public/recorder/report", headers=headers).status_code == 404

    # after round 2: the single table completed everything → auto-available
    _record_round(client, headers, joined["rounds"][1]["id"], audio)
    assert _wait_report_available(client, headers), "report never became auto-available"
    report = client.get("/api/v1/public/recorder/report", headers=headers)
    assert report.status_code == 200
    assert report.json()["published_at"] is None  # available WITHOUT publishing


def test_orchestrated_report_stays_publish_gated(client, tmp_path, monkeypatch):
    from citizens.services import provider_config

    monkeypatch.setattr(provider_config, "analysis_enabled_cached", lambda: False)

    assembly = client.post(
        "/api/v1/assemblies",
        json={"name": "TEST Orch Gate", "recording_mode": "orchestrated",
              "default_table_count": 1,
              "rounds": [{"title": "R1", "question": "Q1", "duration_minutes": 10}]},
    ).json()
    client.post(f"/api/v1/rounds/{assembly['rounds'][0]['id']}/start")
    headers, joined = _join_table1(client, assembly)
    _record_round(client, headers, joined["rounds"][0]["id"], _make_webm_audio(tmp_path))

    # complete, but orchestrated: the organizer must publish explicitly
    assert not _wait_report_available(client, headers, timeout=8.0)
    client.post(f"/api/v1/assemblies/{assembly['id']}/report/publish")
    assert _wait_report_available(client, headers, timeout=5.0)


def test_status_carries_table_summary(client, tmp_path):
    assembly = client.post(
        "/api/v1/assemblies",
        json={"name": "TEST Table Summary", "recording_mode": "independent",
              "default_table_count": 1,
              "rounds": [{"title": "R1", "question": "Q1", "duration_minutes": 10}]},
    ).json()
    headers, joined = _join_table1(client, assembly)
    _record_round(client, headers, joined["rounds"][0]["id"], _make_webm_audio(tmp_path))

    status = client.get("/api/v1/public/recorder/status", headers=headers).json()
    assert status["rounds"][0]["table_summary"] == ""  # not analyzed yet

    # simulate analysis landing (the analysis pipeline has its own tests)
    from sqlalchemy import select

    from citizens.db.models import Recording
    from citizens.db.session import session_scope

    with session_scope() as session:
        recording = session.execute(
            select(Recording).where(Recording.assembly_id == assembly["id"])
        ).scalars().first()
        recording.analysis_summary = "The table discussed parks."

    status = client.get("/api/v1/public/recorder/status", headers=headers).json()
    assert status["rounds"][0]["table_summary"] == "The table discussed parks."
