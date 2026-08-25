"""Closing a session (interim → final, frozen snapshot, recording lock) and the
Files tab (inventory, audio deletion, portable export)."""

import hashlib
import io
import json
import re
import subprocess
import time
import zipfile


def _audio(tmp_path) -> bytes:
    path = tmp_path / "close.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
         "-c:a", "libopus", "-b:a", "32k", str(path)],
        check=True,
        timeout=120,
    )
    return path.read_bytes()


def _assembly(client, name, tables=2, mode="independent"):
    return client.post(
        "/api/v1/assemblies",
        json={"name": name, "recording_mode": mode, "default_table_count": tables,
              "rounds": [{"title": "R1", "question": "Q1", "duration_minutes": 10}]},
    ).json()


def _join(client, assembly, table_index, ip):
    token = re.search(r"#/join/(.+)$", assembly["invites"][table_index]["url"]).group(1)
    joined = client.post(
        "/api/v1/public/join", json={"token": token}, headers={"X-Forwarded-For": ip}
    ).json()
    return {"Authorization": f"Bearer {joined['session_token']}"}, joined


def _record(client, headers, round_id, audio):
    recording_id = client.post(
        "/api/v1/public/recorder/start",
        json={"round_id": round_id, "mime_type": "audio/webm"},
        headers=headers,
    ).json()["recording_id"]
    client.post(
        f"/api/v1/public/recorder/recordings/{recording_id}/chunks/0",
        content=audio,
        headers={**headers, "Content-Type": "application/octet-stream",
                 "X-Chunk-SHA256": hashlib.sha256(audio).hexdigest()},
    )
    client.post(
        f"/api/v1/public/recorder/recordings/{recording_id}/complete",
        json={"total_chunks": 1},
        headers=headers,
    )
    _wait_assembled(client, headers, recording_id)
    return recording_id


def _wait_assembled(client, headers, recording_id, timeout=30.0):
    """The audio file only exists once the background job assembled it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = client.get(
            f"/api/v1/public/recorder/recordings/{recording_id}", headers=headers
        ).json()["state"]
        if state not in ("WAITING_FOR_CHUNKS", "FINALIZING", "ASSEMBLING", "RECORDING"):
            return state
        time.sleep(0.4)
    raise AssertionError(f"recording {recording_id} never assembled")


def test_close_locks_recording_and_finalizes(client, tmp_path):
    assembly = _assembly(client, "TEST Close Lock")
    headers, joined = _join(client, assembly, 0, "10.8.8.1")
    round_id = joined["rounds"][0]["id"]
    _record(client, headers, round_id, _audio(tmp_path))

    # only 1 of 2 tables: interim, and the assembly is under way (not Draft)
    report = client.get(f"/api/v1/assemblies/{assembly['id']}/report").json()
    assert report["is_final"] is False
    assert report["progress"]["tables_complete"] == 1
    assert report["progress"]["tables_expected"] == 2
    assert report["progress"]["tables_missing"] == [2]
    assert client.get(f"/api/v1/assemblies/{assembly['id']}").json()["status"] == "ACTIVE"

    closed = client.post(f"/api/v1/assemblies/{assembly['id']}/close")
    assert closed.status_code == 200 and closed.json()["closed_at"]
    detail = client.get(f"/api/v1/assemblies/{assembly['id']}").json()
    assert detail["status"] == "COMPLETE" and detail["closed_at"]

    report = client.get(f"/api/v1/assemblies/{assembly['id']}/report").json()
    assert report["is_final"] is True

    # a late table can no longer record
    late_headers, late_joined = _join(client, assembly, 1, "10.8.8.2")
    blocked = client.post(
        "/api/v1/public/recorder/start",
        json={"round_id": late_joined["rounds"][0]["id"], "mime_type": "audio/webm"},
        headers=late_headers,
    )
    assert blocked.status_code == 409
    assert "closed" in blocked.json()["detail"].lower()

    # reopening lets them record again
    assert client.delete(f"/api/v1/assemblies/{assembly['id']}/close").status_code == 204
    allowed = client.post(
        "/api/v1/public/recorder/start",
        json={"round_id": late_joined["rounds"][0]["id"], "mime_type": "audio/webm"},
        headers=late_headers,
    )
    assert allowed.status_code == 201


def test_phone_report_frozen_across_reopen(client, tmp_path, monkeypatch):
    from citizens.services import provider_config

    monkeypatch.setattr(provider_config, "analysis_enabled_cached", lambda: False)
    assembly = _assembly(client, "TEST Freeze", tables=1)
    headers, joined = _join(client, assembly, 0, "10.8.8.3")
    _record(client, headers, joined["rounds"][0]["id"], _audio(tmp_path))
    client.post(f"/api/v1/assemblies/{assembly['id']}/close")

    frozen = client.get("/api/v1/public/recorder/report", headers=headers).json()
    assert frozen["is_final"] is True

    # the organizer reopens; participants keep the version they were reading
    client.delete(f"/api/v1/assemblies/{assembly['id']}/close")
    after = client.get("/api/v1/public/recorder/report", headers=headers)
    assert after.status_code == 200
    assert after.json()["is_final"] is True
    assert after.json()["closed_at"] == frozen["closed_at"]


def test_files_listing_download_and_delete(client, tmp_path):
    assembly = _assembly(client, "TEST Files", tables=1)
    headers, joined = _join(client, assembly, 0, "10.8.8.4")
    recording_id = _record(client, headers, joined["rounds"][0]["id"], _audio(tmp_path))

    listing = client.get(f"/api/v1/assemblies/{assembly['id']}/files").json()
    assert listing["totals"]["recordings"] == 1
    assert listing["totals"]["audio_bytes"] > 0
    entry = listing["rounds"][0]["tables"][0]
    assert entry["audio_available"] is True and entry["audio_deleted_at"] is None

    audio = client.get(f"/api/v1/recordings/{recording_id}/audio")
    assert audio.status_code == 200
    assert len(audio.content) > 0
    assert "attachment" in audio.headers["content-disposition"]

    deleted = client.delete(f"/api/v1/recordings/{recording_id}/audio")
    assert deleted.status_code == 200 and deleted.json()["freed_bytes"] > 0

    listing = client.get(f"/api/v1/assemblies/{assembly['id']}/files").json()
    entry = listing["rounds"][0]["tables"][0]
    assert entry["audio_available"] is False and entry["audio_deleted_at"]
    assert listing["totals"]["audio_deleted"] == 1
    # the recording row survives so transcripts/findings keep their context
    assert client.get(f"/api/v1/recordings/{recording_id}/audio").status_code == 404


def test_session_export_zip_is_portable(client, tmp_path):
    assembly = _assembly(client, "TEST Export", tables=1)
    headers, joined = _join(client, assembly, 0, "10.8.8.5")
    _record(client, headers, joined["rounds"][0]["id"], _audio(tmp_path))

    response = client.get(f"/api/v1/assemblies/{assembly['id']}/export.zip")
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert "manifest.json" in names
    assert "report.json" in names and "report.md" in names
    assert "README.txt" in names
    assert any(name.startswith("audio/") for name in names), names

    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["format_version"] == 1
    assert manifest["assembly"]["name"] == "TEST Export"
    assert manifest["recordings"][0]["sha256"]
    assert manifest["recordings"][0]["audio_file"].startswith("audio/")


def test_audio_bundle_zip(client, tmp_path):
    assembly = _assembly(client, "TEST Bundle", tables=1)
    headers, joined = _join(client, assembly, 0, "10.8.8.6")
    _record(client, headers, joined["rounds"][0]["id"], _audio(tmp_path))

    response = client.get(f"/api/v1/assemblies/{assembly['id']}/audio.zip")
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert len(archive.namelist()) == 1
    assert archive.namelist()[0].endswith(".webm")
