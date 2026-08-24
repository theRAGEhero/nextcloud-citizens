"""Provider configuration (STT + analysis) in Nextcloud AppConfig.

API keys are stored with the `sensitive` flag (encrypted by Nextcloud, brief
§28) and are never returned by any API — only `configured` + a short hint.
"""

import time
from typing import Protocol

import httpx

from citizens.logging_setup import get_logger

log = get_logger(__name__)

_LIVE_SNAPSHOT_TTL = 30.0
_live_snapshot: tuple[float, dict] | None = None


def live_stt_snapshot() -> dict:
    """Cached view of the live-STT config — read on every chunk upload, so it
    must not hit Nextcloud's AppConfig OCS API each time."""
    global _live_snapshot
    now = time.monotonic()
    if _live_snapshot is not None and now - _live_snapshot[0] < _LIVE_SNAPSHOT_TTL:
        return _live_snapshot[1]
    try:
        store = default_store()
        provider = get_setting(store, "stt_provider")
        snapshot = {
            "enabled": get_setting(store, "stt_live_enabled") == "1",
            "provider": provider,
            "api_key": store.get_value(f"{provider}_api_key")
            if provider == "deepgram"
            else store.get_value("mistral_api_key"),
            "model": get_setting(store, "deepgram_live_model")
            if provider == "deepgram"
            else get_setting(store, "mistral_live_model"),
        }
    except Exception:
        log.warning("live_stt_snapshot_failed", exc_info=True)
        snapshot = {"enabled": False, "provider": "", "api_key": None, "model": ""}
    _live_snapshot = (now, snapshot)
    return snapshot


def invalidate_snapshot() -> None:
    global _live_snapshot, _analysis_enabled_cache
    _live_snapshot = None
    _analysis_enabled_cache = None


_analysis_enabled_cache: tuple[float, bool] | None = None


def analysis_enabled_cached() -> bool:
    """Cached analysis-enabled flag for hot public endpoints (status polls
    hit this; AppConfig OCS reads are too slow for every poll)."""
    global _analysis_enabled_cache
    now = time.monotonic()
    if _analysis_enabled_cache is not None and now - _analysis_enabled_cache[0] < _LIVE_SNAPSHOT_TTL:
        return _analysis_enabled_cache[1]
    try:
        enabled = get_setting(default_store(), "analysis_enabled") == "1"
    except Exception:
        enabled = True  # assume the stricter completion gate when unreachable
    _analysis_enabled_cache = (now, enabled)
    return enabled

KEY_FIELDS = ("mistral_api_key", "deepgram_api_key", "analysis_api_key")

DEFAULTS = {
    "stt_provider": "mistral",
    "stt_live_enabled": "1",
    "stt_batch_enabled": "1",
    # model IDs verified against provider docs 2026-08-23; live and final
    # (batch) transcription models are configured separately per provider
    "deepgram_live_model": "nova-3",
    "deepgram_batch_model": "nova-3",
    "mistral_live_model": "",  # Voxtral Realtime — not wired yet
    "mistral_batch_model": "voxtral-mini-latest",
    "analysis_base_url": "https://api.mistral.ai/v1",
    "analysis_model": "mistral-large-latest",
    "analysis_enabled": "1",
    # appended to the built-in analysis prompts (tone, focus areas, glossary);
    # the JSON output contract and evidence rules stay protected
    "analysis_extra_instructions": "",
    # shown with the logo on PDF report headers/footers
    "organization_name": "",
}

# reads of the new split keys fall back to the pre-split stored values
LEGACY_KEYS = {
    "deepgram_live_model": "deepgram_model",
    "deepgram_batch_model": "deepgram_model",
    "mistral_batch_model": "mistral_stt_model",
}


class ConfigStore(Protocol):
    def get_value(self, key: str) -> str | None: ...

    def set_value(self, key: str, value: str, sensitive: bool = False) -> None: ...

    def delete_value(self, key: str) -> None: ...


def default_store() -> "AppConfigStore":
    """Store for non-request contexts (background jobs). Builds its own
    NextcloudApp client from the AppAPI environment."""
    from nc_py_api import NextcloudApp

    return AppConfigStore(NextcloudApp())


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
    if (value is None or value == "") and key in LEGACY_KEYS:
        value = store.get_value(LEGACY_KEYS[key])
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
        "organization_name": get_setting(store, "organization_name"),
        "stt": {
            "provider": get_setting(store, "stt_provider"),
            "live_enabled": get_setting(store, "stt_live_enabled") == "1",
            "batch_enabled": get_setting(store, "stt_batch_enabled") == "1",
            "mistral_configured": bool(store.get_value("mistral_api_key")),
            "mistral_key_hint": key_hint(store, "mistral_api_key"),
            "mistral_live_model": get_setting(store, "mistral_live_model"),
            "mistral_batch_model": get_setting(store, "mistral_batch_model"),
            "deepgram_configured": bool(store.get_value("deepgram_api_key")),
            "deepgram_key_hint": key_hint(store, "deepgram_api_key"),
            "deepgram_live_model": get_setting(store, "deepgram_live_model"),
            "deepgram_batch_model": get_setting(store, "deepgram_batch_model"),
        },
        "analysis": {
            "base_url": get_setting(store, "analysis_base_url"),
            "model": get_setting(store, "analysis_model"),
            "configured": bool(store.get_value("analysis_api_key")),
            "key_hint": key_hint(store, "analysis_api_key"),
            "enabled": get_setting(store, "analysis_enabled") == "1",
            "extra_instructions": get_setting(store, "analysis_extra_instructions"),
        },
    }


def test_connection(
    store: ConfigStore,
    target: str,
    override_key: str | None = None,
    override_base_url: str | None = None,
) -> dict:
    """Verify credentials against the provider. `override_key` lets the admin
    test a key typed into the form BEFORE saving it. Never logs or returns
    key material."""
    try:
        if target == "mistral":
            key = override_key or store.get_value("mistral_api_key")
            if not key:
                return {"ok": False, "message": "No Mistral API key — paste one or save it first"}
            response = httpx.get(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=15,
            )
        elif target == "deepgram":
            key = override_key or store.get_value("deepgram_api_key")
            if not key:
                return {"ok": False, "message": "No Deepgram API key — paste one or save it first"}
            response = httpx.get(
                "https://api.deepgram.com/v1/auth/token",
                headers={"Authorization": f"Token {key}"},
                timeout=15,
            )
        elif target == "analysis":
            key = override_key or store.get_value("analysis_api_key")
            if not key:
                return {"ok": False, "message": "No analysis API key — paste one or save it first"}
            base = (override_base_url or get_setting(store, "analysis_base_url")).rstrip("/")
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
