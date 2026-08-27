# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provider selection: every engine must be reachable through the dispatch,
gated on its own credentials, and never fall back to another provider's key."""

import pytest

from citizens.providers.transcription.base import (
    NormalizedSegment,
    NormalizedTranscript,
    TranscriptionError,
)
from citizens.services import provider_config
from citizens.services import transcription as transcription_svc


class MemoryStore:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_value(self, key):
        return self.values.get(key)

    def set_value(self, key, value, sensitive=False):
        self.values[key] = value

    def delete_value(self, key):
        self.values.pop(key, None)


def _transcript(provider):
    return NormalizedTranscript(
        provider=provider, model="m", language="en",
        segments=[NormalizedSegment(speaker="", start=0.0, end=1.0, text="hello")],
        raw={},
    )


@pytest.mark.parametrize(
    "settings,ready",
    [
        ({"stt_provider": "deepgram", "deepgram_api_key": "dg"}, True),
        ({"stt_provider": "deepgram"}, False),
        ({"stt_provider": "mistral", "mistral_api_key": "mk"}, True),
        # a Whisper server is identified by its URL, not a key; an empty stored
        # value falls back to the default endpoint, so these stay ready and a
        # wrong endpoint surfaces as a failed job rather than silence
        ({"stt_provider": "whisper"}, True),
        ({"stt_provider": "whisper", "whisper_base_url": ""}, True),
        ({"stt_provider": "vosk"}, True),
        ({"stt_provider": "vosk", "vosk_url": ""}, True),
        ({"stt_provider": "nope"}, False),
    ],
)
def test_batch_ready_uses_each_provider_own_credentials(settings, ready):
    store = MemoryStore({"stt_batch_enabled": "1", **settings})
    assert transcription_svc.batch_transcription_ready(store) is ready


def test_batch_ready_false_when_disabled():
    store = MemoryStore({"stt_batch_enabled": "0", "stt_provider": "vosk"})
    assert transcription_svc.batch_transcription_ready(store) is False


def test_live_snapshot_never_borrows_another_providers_key(monkeypatch):
    store = MemoryStore({
        "stt_provider": "whisper",
        "mistral_api_key": "SHOULD-NOT-BE-USED",
        "whisper_api_key": "wk",
        "whisper_live_model": "",
    })
    monkeypatch.setattr(provider_config, "default_store", lambda: store)
    provider_config.invalidate_snapshot()
    snapshot = provider_config.live_stt_snapshot()
    provider_config.invalidate_snapshot()
    assert snapshot["provider"] == "whisper"
    assert snapshot["api_key"] == "wk"


@pytest.mark.parametrize("provider,module,settings", [
    ("whisper", "whisper_provider", {"whisper_base_url": "http://whisper.local/v1"}),
    ("vosk", "vosk_provider", {"vosk_url": "ws://vosk.local:2700"}),
])
def test_dispatch_calls_the_selected_adapter(provider, module, settings, monkeypatch, tmp_path):
    calls = {}

    def fake_transcribe(api_key, path, mime, language, model="", base_url=""):
        calls["api_key"] = api_key
        calls["base_url"] = base_url
        return _transcript(provider)

    monkeypatch.setattr(
        getattr(transcription_svc, module), "transcribe_file", fake_transcribe
    )

    class Recording:
        id = "rec"
        assembly_id = "asm"
        canonical_audio_path = "audio.webm"
        mime_type = "audio/webm"

    audio = tmp_path / "storage" / "audio.webm"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x")

    from citizens.config import get_settings

    monkeypatch.setenv("APP_PERSISTENT_STORAGE", str(tmp_path / "storage"))
    get_settings.cache_clear()

    store = MemoryStore({"stt_provider": provider, **settings})
    stored = {}

    monkeypatch.setattr(transcription_svc, "store_transcript",
                        lambda session, recording, normalized: stored.setdefault("n", normalized))

    class Session:
        def get(self, model, ident):
            return None

        def commit(self):
            pass

    transcription_svc.transcribe_recording(Session(), store, Recording())
    get_settings.cache_clear()
    assert stored["n"].provider == provider
    assert calls["base_url"] == list(settings.values())[0]


def test_dispatch_rejects_unconfigured_endpoint(monkeypatch, tmp_path):
    class Recording:
        id = "rec"
        assembly_id = "asm"
        canonical_audio_path = "audio.webm"
        mime_type = "audio/webm"

    audio = tmp_path / "storage" / "audio.webm"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x")

    from citizens.config import get_settings

    monkeypatch.setenv("APP_PERSISTENT_STORAGE", str(tmp_path / "storage"))
    get_settings.cache_clear()

    class Session:
        def get(self, model, ident):
            return None

        def commit(self):
            pass

    store = MemoryStore({"stt_provider": "vosk", "vosk_url": ""})
    with pytest.raises(TranscriptionError) as excinfo:
        transcription_svc.transcribe_recording(Session(), store, Recording())
    get_settings.cache_clear()
    assert excinfo.value.permanent is True


class _VoskStore:
    def __init__(self, mapping):
        self.values = {"vosk_language_models": mapping} if mapping is not None else {}

    def get_value(self, key):
        return self.values.get(key)

    def set_value(self, key, value, sensitive=False):
        self.values[key] = value

    def delete_value(self, key):
        self.values.pop(key, None)


def test_vosk_model_is_chosen_by_the_session_language():
    """One Vosk server holds a model per language; the assembly's language
    selects it. Without this every language would hit the same model and the
    transcript would be nonsense for all but one of them."""
    store = _VoskStore('{"it": "/models/it", "en": "/models/en"}')
    assert provider_config.vosk_model_for(store, "it") == "/models/it"
    assert provider_config.vosk_model_for(store, "en") == "/models/en"
    # a regional code must still find its language
    assert provider_config.vosk_model_for(store, "it-IT") == "/models/it"
    assert provider_config.vosk_model_for(store, "EN") == "/models/en"
    # an unmapped language sends no model, so the server default still works
    assert provider_config.vosk_model_for(store, "de") == ""


def test_vosk_model_map_survives_bad_configuration():
    """A corrupt map must degrade to the server default, never stop a recording
    from being transcribed."""
    assert provider_config.vosk_model_for(_VoskStore(None), "it") == ""
    assert provider_config.vosk_model_for(_VoskStore(""), "it") == ""
    assert provider_config.vosk_model_for(_VoskStore("not json"), "it") == ""
    assert provider_config.vosk_model_for(_VoskStore('["a", "b"]'), "it") == ""
    assert provider_config.vosk_model_for(_VoskStore('{"it": ""}'), "it") == ""


def test_live_captions_pick_the_model_for_the_table_language():
    """The caption path resolves from the cached snapshot, so it must agree
    with the batch resolver — and must never make an OCS call per chunk."""
    from citizens.services.live_captions import LIVE_CAPTIONS

    snapshot = {"vosk_models": {"it": "/models/it", "en": "/models/en"}}
    assert LIVE_CAPTIONS._resolve_vosk_model(snapshot, "it") == "/models/it"
    assert LIVE_CAPTIONS._resolve_vosk_model(snapshot, "it-IT") == "/models/it"
    assert LIVE_CAPTIONS._resolve_vosk_model(snapshot, "de") == ""
    assert LIVE_CAPTIONS._resolve_vosk_model({}, "it") == ""


def test_vosk_client_sends_the_model_it_was_given():
    """The config frame must carry the model, otherwise the mapping is
    cosmetic: every language would land on whatever the server loaded first."""
    import asyncio
    import json as jsonlib

    from citizens.providers.transcription import vosk as vosk_provider

    sent = []

    class _FakeSocket:
        async def send(self, message):
            sent.append(message)

        async def recv(self):
            return jsonlib.dumps({"text": ""})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    def fake_connect(*_args, **_kwargs):
        return _FakeSocket()

    import websockets.asyncio.client as ws_client

    original = ws_client.connect
    ws_client.connect = fake_connect
    try:
        asyncio.run(vosk_provider._stream("ws://x:2700", b"\0" * 640, "/models/it"))
        config = jsonlib.loads(sent[0])["config"]
        assert config["model"] == "/models/it"
        assert config["sample_rate"] == vosk_provider.SAMPLE_RATE

        sent.clear()
        asyncio.run(vosk_provider._stream("ws://x:2700", b"\0" * 640, ""))
        assert "model" not in jsonlib.loads(sent[0])["config"]
    finally:
        ws_client.connect = original
