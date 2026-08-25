# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
from fastapi.testclient import TestClient

from citizens.main import create_app


def test_health_endpoint(settings_env):
    app = create_app(with_auth=False)
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["app"] == "citizens"
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["storage"] == "ok"
    assert body["disk_free_gb"] is not None
