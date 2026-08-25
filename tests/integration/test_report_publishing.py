# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Report publishing to table phones, PDF rendering, invite link re-viewing."""

import base64
import re


def _make_assembly(client, name="TEST Publish"):
    return client.post(
        "/api/v1/assemblies",
        json={"name": name, "default_table_count": 1,
              "rounds": [{"title": "R1", "question": "Q", "duration_minutes": 10}]},
    ).json()


def _join(client, assembly, ip):
    token = re.search(r"#/join/(.+)$", assembly["invites"][0]["url"]).group(1)
    joined = client.post(
        "/api/v1/public/join", json={"token": token}, headers={"X-Forwarded-For": ip}
    ).json()
    return {"Authorization": f"Bearer {joined['session_token']}"}


def test_phone_report_gated_by_publication(client):
    assembly = _make_assembly(client, "TEST Publish Gate")
    headers = _join(client, assembly, "10.9.9.1")

    assert client.get("/api/v1/public/recorder/report", headers=headers).status_code == 404
    status = client.get("/api/v1/public/recorder/status", headers=headers).json()
    assert status["report_available"] is False

    published = client.post(f"/api/v1/assemblies/{assembly['id']}/report/publish")
    assert published.status_code == 200 and published.json()["published_at"]

    status = client.get("/api/v1/public/recorder/status", headers=headers).json()
    assert status["report_available"] is True
    report = client.get("/api/v1/public/recorder/report", headers=headers).json()
    assert report["assembly"]["name"] == "TEST Publish Gate"
    assert report["include_drafts"] is False  # drafts never reach participants
    assert report["published_at"]

    pdf = client.get("/api/v1/public/recorder/report.pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    assert client.delete(f"/api/v1/assemblies/{assembly['id']}/report/publish").status_code == 204
    assert client.get("/api/v1/public/recorder/report", headers=headers).status_code == 404


def test_organizer_pdf_download(client):
    assembly = _make_assembly(client, "TEST Organizer PDF")
    # interim: no export until the organizer closes the session
    assert client.get(f"/api/v1/assemblies/{assembly['id']}/report.pdf").status_code == 409

    client.post(f"/api/v1/assemblies/{assembly['id']}/close")
    response = client.get(f"/api/v1/assemblies/{assembly['id']}/report.pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert "attachment" in response.headers["content-disposition"]


def test_invite_links_reviewable(client):
    assembly = _make_assembly(client, "TEST Relink")
    links = client.get(f"/api/v1/assemblies/{assembly['id']}/invites/links").json()
    assert len(links) == 1
    # the re-materialized link matches the one issued at creation
    assert links[0]["url"] == assembly["invites"][0]["url"]
    assert links[0]["qr_svg"].startswith("<svg")

    # regenerating revokes and produces different links, still re-viewable
    fresh = client.post(f"/api/v1/assemblies/{assembly['id']}/invites/generate").json()
    relisted = client.get(f"/api/v1/assemblies/{assembly['id']}/invites/links").json()
    assert relisted[0]["url"] == fresh[0]["url"] != assembly["invites"][0]["url"]


PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
    "h6FO1AAAAABJRU5ErkJggg=="
)


def test_logo_roundtrip(client):
    from citizens.api.admin import get_config_store

    class MemoryStore:
        def __init__(self):
            self.values = {}

        def get_value(self, key):
            return self.values.get(key, "")

        def set_value(self, key, value, sensitive=False):
            self.values[key] = value

        def delete_value(self, key):
            self.values.pop(key, None)

    client.app.dependency_overrides[get_config_store] = lambda: MemoryStore()

    assert client.get("/api/v1/admin/logo").status_code == 404
    upload = client.put(
        "/api/v1/admin/logo", json={"data": base64.b64encode(PNG_1PX).decode()}
    )
    assert upload.status_code == 204
    fetched = client.get("/api/v1/admin/logo")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/png"
    assert fetched.content == PNG_1PX
    assert client.get("/api/v1/admin/providers").json()["logo_set"] is True

    rejected = client.put("/api/v1/admin/logo", json={"data": base64.b64encode(b"GIF89a").decode()})
    assert rejected.status_code == 422

    assert client.delete("/api/v1/admin/logo").status_code == 204
    assert client.get("/api/v1/admin/logo").status_code == 404


def test_delete_assembly_purges_stored_audio(client, settings_env):
    assembly = _make_assembly(client, "TEST Purge")
    root = settings_env.app_persistent_storage
    for subdir in ("recordings", "assembled"):
        target = root / subdir / assembly["id"] / "x"
        target.mkdir(parents=True)
        (target / "chunk.bin").write_bytes(b"audio")

    assert client.delete(f"/api/v1/assemblies/{assembly['id']}").status_code in (200, 204)
    assert not (root / "recordings" / assembly["id"]).exists()
    assert not (root / "assembled" / assembly["id"]).exists()
