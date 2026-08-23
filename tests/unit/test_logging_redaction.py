from citizens.logging_setup import REDACTED, redaction_processor


def test_sensitive_keys_are_redacted():
    event = {
        "event": "provider_configured",
        "api_key": "sk-live-abcdef",
        "Authorization": "Bearer xyz",
        "recorder_token": "tok",
        "password": "hunter2",
        "provider": "mistral",
    }
    result = redaction_processor(None, None, event)
    assert result["api_key"] == REDACTED
    assert result["Authorization"] == REDACTED
    assert result["recorder_token"] == REDACTED
    assert result["password"] == REDACTED
    assert result["provider"] == "mistral"
    assert result["event"] == "provider_configured"


def test_redaction_is_recursive():
    event = {
        "event": "x",
        "payload": {"config": {"deepgram_api_key": "abc"}, "items": [{"secret": "s"}, {"ok": 1}]},
    }
    result = redaction_processor(None, None, event)
    assert result["payload"]["config"]["deepgram_api_key"] == REDACTED
    assert result["payload"]["items"][0]["secret"] == REDACTED
    assert result["payload"]["items"][1]["ok"] == 1
