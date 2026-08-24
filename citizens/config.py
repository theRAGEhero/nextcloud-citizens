"""Application configuration from environment variables (provided by AppAPI)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # Provided by AppAPI / the container environment
    app_id: str = "citizens"
    app_version: str = "0.4.0"
    app_host: str = "0.0.0.0"
    app_port: int = 23000
    app_secret: str = ""
    nextcloud_url: str = ""
    app_persistent_storage: Path = Path("persistent_storage")

    # Citizens-specific
    citizens_log_level: str = "INFO"
    citizens_dev: bool = False
    # ONLY for local browser tests: disables AppAPI signature auth entirely.
    # Never set on an instance reachable by anyone else.
    citizens_insecure_no_auth: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
