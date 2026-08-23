"""Provider configuration (STT + analysis) in Nextcloud AppConfig.

API keys are stored with the `sensitive` flag (encrypted by Nextcloud, brief
§28) and are never returned by any API — only `configured` + a short hint.
"""

from typing import Protocol

import httpx

from citizens.logging_setup import get_logger

log = get_logger(__name__)

KEY_FIELDS = ("mistral_api_key", "deepgram_api_key", "analysis_api_key")

DEFAULTS = {
    "stt_provider": "mistral",
    "stt_live_enabled": "1",
    "stt_batch_enabled": "1",
    "analysis_base_url": "https://api.mistral.ai/v1",
    "analysis_model": "mistral-large-latest",
}


class ConfigStore(Protocol):
    def get_value(self, key: str) -> str | None: ...

    def set_value(self, key: str, value: str, sensitive: bool = False) -> None: ...

    def delete_value(self, key: str) -> None: ...


class AppConfigStore:
    """Nextcloud AppConfigEx-backed store (values scoped to this ExApp)."""

    def __init__(self, nc):
        self._nc = nc

    def get_value(self, key: str) -> str | None:
        return self._nc.appconfig_ex.get_value(key)

    def set_value(self, key: str, value: str, sensitive: bool = False) -> None:
        self._nc.appconfig_ex.set_value(key, value, sensitive=sensitive)

    def delete_value(self, key: str) -> None:
        self._nc.appconfig_ex.delete(key)


def get_setting(store: ConfigStore, key: str) -> str:
    value = store.get_value(key)
    if value is None or value == "":
        return DEFAULTS.get(key, "")
    return value


def set_settings(store: ConfigStore, values: dict[str, str]) -> list[str]:
    """Store the provided fields; empty string clears a key field. Returns the
    list of field names changed (for audit — never the values)."""
    changed = []
    for key, value in values.items():
        sensitive = key in KEY_FIELDS
        if sensitive and value == "":
            store.delete_value(key)
        else:
            store.set_value(key, value, sensitive=sensitive)
        changed.append(key)
    return changed


def key_hint(store: ConfigStore, key: str) -> str:
    value = store.get_value(key)
    if not value:
        return ""
    return f"…{value[-4:]}" if len(value) >= 8 else "…"


def providers_summary(store: ConfigStore) -> dict:
    return {
        "stt": {
            "provider": get_setting(store, "stt_provider"),
            "live_enabled": get_setting(store, "stt_live_enabled") == "1",
            "batch_enabled": get_setting(store, "stt_batch_enabled") == "1",
            "mistral_configured": bool(store.get_value("mistral_api_key")),
            "mistral_key_hint": key_hint(store, "mistral_api_key"),
            "deepgram_configured": bool(store.get_value("deepgram_api_key")),
            "deepgram_key_hint": key_hint(store, "deepgram_api_key"),
        },
        "analysis": {
            "base_url": get_setting(store, "analysis_base_url"),
            "model": get_setting(store, "analysis_model"),
            "configured": bool(store.get_value("analysis_api_key")),
            "key_hint": key_hint(store, "analysis_api_key"),
        },
    }


def test_connection(store: ConfigStore, target: str) -> dict:
    """Verify stored credentials against the provider. Never logs or returns
    key material."""
    try:
        if target == "mistral":
            key = store.get_value("mistral_api_key")
            if not key:
                return {"ok": False, "message": "No Mistral API key configured"}
            response = httpx.get(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=15,
            )
        elif target == "deepgram":
            key = store.get_value("deepgram_api_key")
            if not key:
                return {"ok": False, "message": "No Deepgram API key configured"}
            response = httpx.get(
                "https://api.deepgram.com/v1/auth/token",
                headers={"Authorization": f"Token {key}"},
                timeout=15,
            )
        elif target == "analysis":
            key = store.get_value("analysis_api_key")
            if not key:
                return {"ok": False, "message": "No analysis API key configured"}
            base = get_setting(store, "analysis_base_url").rstrip("/")
            response = httpx.get(
                f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=15
            )
        else:
            return {"ok": False, "message": f"Unknown target {target}"}
    except httpx.HTTPError as exc:
        log.warning("provider_test_failed", target=target, error=type(exc).__name__)
        return {"ok": False, "message": f"Connection failed: {type(exc).__name__}"}

    ok = response.status_code == 200
    log.info("provider_test", target=target, status=response.status_code, ok=ok)
    if ok:
        return {"ok": True, "message": "Connected"}
    if response.status_code in (401, 403):
        return {"ok": False, "message": f"Authentication failed (HTTP {response.status_code})"}
    return {"ok": False, "message": f"Provider returned HTTP {response.status_code}"}
