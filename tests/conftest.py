import pytest

from citizens.config import get_settings


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
