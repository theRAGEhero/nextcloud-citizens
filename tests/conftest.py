# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from citizens.config import get_settings
from citizens.main import create_app
from citizens.security.identity import get_current_user_id


@pytest.fixture
def settings_env(tmp_path, monkeypatch):
    """Point the app at a temporary storage dir and return fresh settings."""
    monkeypatch.setenv("APP_ID", "citizens")
    monkeypatch.setenv("APP_VERSION", "0.0.0-test")
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("NEXTCLOUD_URL", "http://nextcloud.test")
    monkeypatch.setenv("APP_PERSISTENT_STORAGE", str(tmp_path / "storage"))
    monkeypatch.setenv("CITIZENS_DEV", "0")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def client(settings_env):
    """App without AppAPI signature auth; identity comes from the X-Test-User
    header (default 'tester') so ownership rules can be exercised."""
    app = create_app(with_auth=False)

    def fake_user(request: Request) -> str:
        return request.headers.get("x-test-user", "tester")

    app.dependency_overrides[get_current_user_id] = fake_user
    with TestClient(app) as test_client:
        yield test_client
