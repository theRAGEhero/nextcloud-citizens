# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recording modes: orchestrated gating, independent freedom, arming, auto-QR."""

import re


def _join(client, assembly, ip):
    invites = assembly.get("invites") or client.post(
        f"/api/v1/assemblies/{assembly['id']}/invites/generate"
    ).json()
    token = re.search(r"#/join/(.+)$", invites[0]["url"]).group(1)
    return client.post(
        "/api/v1/public/join", json={"token": token}, headers={"X-Forwarded-For": ip}
    ).json()


def test_create_auto_generates_qr_codes(client):
    created = client.post(
        "/api/v1/assemblies",
        json={"name": "TEST AutoQR", "default_table_count": 3,
              "rounds": [{"title": "R1", "question": "Q", "duration_minutes": 10}]},
    ).json()
    assert len(created["invites"]) == 3
    assert all("recorder.html#/join/" in invite["url"] for invite in created["invites"])
    listing = client.get(f"/api/v1/assemblies/{created['id']}/invites").json()
    assert len(listing) == 3 and all(invite["active"] for invite in listing)


def test_orchestrated_blocks_start_until_round_active(client):
    created = client.post(
        "/api/v1/assemblies",
        json={"name": "TEST Orchestrated", "recording_mode": "orchestrated",
              "default_table_count": 1,
              "rounds": [{"title": "R1", "question": "Q", "duration_minutes": 10}]},
    ).json()
    joined = _join(client, created, "10.5.5.1")
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    assert joined["assembly"]["recording_mode"] == "orchestrated"

    blocked = client.post(
        "/api/v1/public/recorder/start",
        json={"round_id": joined["rounds"][0]["id"], "mime_type": "audio/webm"},
        headers=headers,
    )
    assert blocked.status_code == 409
    assert "facilitator has not started" in blocked.json()["detail"]

    client.post(f"/api/v1/rounds/{joined['rounds'][0]['id']}/start")
    allowed = client.post(
        "/api/v1/public/recorder/start",
        json={"round_id": joined["rounds"][0]["id"], "mime_type": "audio/webm"},
        headers=headers,
    )
    assert allowed.status_code == 201


def test_independent_records_without_facilitator(client):
    created = client.post(
        "/api/v1/assemblies",
        json={"name": "TEST Independent", "recording_mode": "independent",
              "default_table_count": 1,
              "rounds": [{"title": "R1", "question": "Q", "duration_minutes": 10}]},
    ).json()
    joined = _join(client, created, "10.5.5.2")
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    # no round started by anyone — the table records on its own schedule
    allowed = client.post(
        "/api/v1/public/recorder/start",
        json={"round_id": joined["rounds"][0]["id"], "mime_type": "audio/webm"},
        headers=headers,
    )
    assert allowed.status_code == 201


def test_armed_heartbeat_feeds_readiness(client):
    created = client.post(
        "/api/v1/assemblies",
        json={"name": "TEST Arming", "recording_mode": "orchestrated",
              "default_table_count": 2,
              "rounds": [{"title": "R1", "question": "Q", "duration_minutes": 10}]},
    ).json()
    joined = _join(client, created, "10.5.5.3")
    headers = {"Authorization": f"Bearer {joined['session_token']}"}
    round_id = joined["rounds"][0]["id"]

    monitor = client.get(f"/api/v1/rounds/{round_id}/monitor").json()
    assert monitor["recording_mode"] == "orchestrated"
    assert monitor["tables_ready"] == 0 and monitor["tables_total"] == 2

    client.post(
        "/api/v1/public/recorder/heartbeat",
        json={"recording_active": False, "armed": True, "storage_ok": True},
        headers=headers,
    )
    monitor = client.get(f"/api/v1/rounds/{round_id}/monitor").json()
    assert monitor["tables_ready"] == 1
    armed_table = next(t for t in monitor["tables"] if t["number"] == 1)
    assert armed_table["armed"] is True
