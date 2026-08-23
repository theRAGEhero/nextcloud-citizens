"""Admin provider settings: keys stored sensitively, never returned, hints only."""

import pytest

from citizens.api.admin import get_config_store
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
    return client, store


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
