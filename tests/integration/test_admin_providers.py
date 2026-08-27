# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Admin provider settings: keys stored sensitively, never returned, hints only."""

import pytest

from citizens.api.admin import get_config_store, require_admin
from citizens.services import provider_config


class MemoryStore:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.sensitive_keys: set[str] = set()

    def get_value(self, key):
        return self.values.get(key)

    def set_value(self, key, value, sensitive=False):
        self.values[key] = value
        if sensitive:
            self.sensitive_keys.add(key)

    def delete_value(self, key):
        self.values.pop(key, None)


@pytest.fixture
def admin_client(client):
    store = MemoryStore()
    client.app.dependency_overrides[get_config_store] = lambda: store
    # the real check asks Nextcloud for group membership; see
    # test_non_admin_is_refused for the negative case
    client.app.dependency_overrides[require_admin] = lambda: "tester"
    return client, store


def test_non_admin_is_refused_by_the_app_not_only_the_proxy(client, monkeypatch):
    """The proxy restricts these paths to administrators, but that is one regex
    in info.xml. These endpoints read and write provider API keys, so the app
    checks too."""
    from citizens.api import admin

    class _User:
        groups = ["users"]

    class _NC:
        class users:
            @staticmethod
            def get_details(user_id):
                return _User()

    assert admin.require_admin.__doc__  # documented as defence in depth
    with pytest.raises(Exception) as excinfo:
        admin.require_admin(_NC(), "someone")
    assert getattr(excinfo.value, "status_code", None) == 403

    class _Broken:
        class users:
            @staticmethod
            def get_details(user_id):
                raise RuntimeError("Nextcloud unreachable")

    with pytest.raises(Exception) as excinfo:
        admin.require_admin(_Broken(), "someone")
    assert getattr(excinfo.value, "status_code", None) == 503  # fails closed


def test_defaults(admin_client):
    client, _ = admin_client
    summary = client.get("/api/v1/admin/providers").json()
    assert summary["stt"]["provider"] == "mistral"
    assert summary["stt"]["mistral_configured"] is False
    assert summary["analysis"]["base_url"] == "https://api.mistral.ai/v1"
    assert summary["analysis"]["configured"] is False


def test_store_keys_returns_hints_only(admin_client):
    client, store = admin_client
    response = client.put(
        "/api/v1/admin/providers",
        json={
            "stt_provider": "deepgram",
            "deepgram_api_key": "dg-secret-key-ABCD1234",
            "analysis_api_key": "sk-analysis-key-WXYZ9876",
            "analysis_base_url": "https://ollama.example.com/v1",
            "analysis_model": "qwen3:32b",
        },
    )
    assert response.status_code == 200
    body = response.json()
    # never the key itself, anywhere in the response
    assert "dg-secret-key" not in response.text
    assert "sk-analysis-key" not in response.text
    assert body["stt"]["provider"] == "deepgram"
    assert body["stt"]["deepgram_configured"] is True
    assert body["stt"]["deepgram_key_hint"] == "…1234"
    assert body["analysis"]["configured"] is True
    assert body["analysis"]["key_hint"] == "…9876"
    assert body["analysis"]["base_url"] == "https://ollama.example.com/v1"
    # keys were flagged sensitive in the store
    assert "deepgram_api_key" in store.sensitive_keys
    assert "analysis_api_key" in store.sensitive_keys


def test_clear_key_with_empty_string(admin_client):
    client, store = admin_client
    client.put("/api/v1/admin/providers", json={"mistral_api_key": "mk-123456789"})
    assert store.get_value("mistral_api_key") == "mk-123456789"
    body = client.put("/api/v1/admin/providers", json={"mistral_api_key": ""}).json()
    assert store.get_value("mistral_api_key") is None
    assert body["stt"]["mistral_configured"] is False


def test_connection_test_without_key(admin_client):
    client, _ = admin_client
    result = client.post("/api/v1/admin/providers/test", json={"target": "mistral"}).json()
    assert result["ok"] is False
    assert "No Mistral API key" in result["message"]


def test_connection_test_mocked(admin_client, monkeypatch):
    client, store = admin_client
    store.set_value("mistral_api_key", "mk-test", sensitive=True)

    class FakeResponse:
        status_code = 200

    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["auth"] = headers.get("Authorization", "")
        return FakeResponse()

    monkeypatch.setattr(provider_config.httpx, "get", fake_get)
    result = client.post("/api/v1/admin/providers/test", json={"target": "mistral"}).json()
    assert result == {"ok": True, "message": "Connected"}
    assert captured["url"] == "https://api.mistral.ai/v1/models"
    assert captured["auth"] == "Bearer mk-test"


def test_saved_key_is_never_sent_to_a_typed_in_endpoint(admin_client, monkeypatch):
    """Testing a connection must not become a way to read the stored key back.

    `api_key` and `base_url` are independent fields, so naming only a URL used
    to make the server send the SAVED key as a Bearer token to that host.
    """
    client, store = admin_client
    store.set_value("analysis_api_key", "sk-stored-secret-0001", sensitive=True)

    reached = {}

    def fake_get(url, headers=None, timeout=None):
        reached["url"] = url
        reached["auth"] = (headers or {}).get("Authorization", "")

        class FakeResponse:
            status_code = 200

        return FakeResponse()

    monkeypatch.setattr(provider_config.httpx, "get", fake_get)
    result = client.post(
        "/api/v1/admin/providers/test",
        json={"target": "analysis", "base_url": "https://attacker.example"},
    ).json()

    assert result["ok"] is False
    assert reached == {}, f"stored key was sent to {reached.get('url')}"
    # the same request with an explicit key is still allowed
    allowed = client.post(
        "/api/v1/admin/providers/test",
        json={"target": "analysis", "base_url": "https://ollama.example/v1", "api_key": "sk-typed"},
    ).json()
    assert allowed == {"ok": True, "message": "Connected"}
    assert reached["auth"] == "Bearer sk-typed"


def test_update_is_audited_without_values(admin_client):
    client, _ = admin_client
    client.put("/api/v1/admin/providers", json={"mistral_api_key": "mk-super-secret-999"})
    # the audit trail must reference the field name, never the value
    from sqlalchemy import select

    from citizens.db.models import AuditEvent
    from citizens.db.session import session_scope

    with session_scope() as session:
        events = [
            e for e in session.execute(select(AuditEvent)).scalars()
            if e.event == "providers_updated"
        ]
    assert events, "providers_updated audit event missing"
    assert "mistral_api_key" in events[-1].data_json
    assert "mk-super-secret-999" not in events[-1].data_json


def test_participant_notice_follows_the_endpoint_not_the_engine_name(admin_client):
    """Whisper and Vosk are self-hosted in the usual case, but nothing stops an
    admin pointing them at a public server — and the table must not be told
    "stays on our server" when it does not."""
    _, store = admin_client

    store.set_value("stt_provider", "whisper")
    for local in (
        "http://speaches:8000/v1",            # container name on the docker network
        "http://192.168.1.50:8000/v1",        # LAN address
        "http://localhost:8000/v1",
        "http://whisper.internal:8000/v1",    # private-use suffix
    ):
        store.set_value("whisper_base_url", local)
        assert provider_config.stt_is_hosted(store, "whisper") is False, local

    store.set_value("whisper_base_url", "https://api.openai.com/v1")
    assert provider_config.stt_is_hosted(store, "whisper") is True

    # hosted services are always hosted, whatever else is configured
    assert provider_config.stt_is_hosted(store, "deepgram") is True


def test_endpoints_must_be_real_urls(admin_client):
    client, _ = admin_client
    rejected = client.put(
        "/api/v1/admin/providers", json={"whisper_base_url": "file:///etc/passwd"}
    )
    assert rejected.status_code == 422
    assert client.put(
        "/api/v1/admin/providers", json={"vosk_url": "https://not-a-websocket.example"}
    ).status_code == 422
    assert client.put(
        "/api/v1/admin/providers", json={"vosk_url": "ws://vosk.internal:2700"}
    ).status_code == 200
