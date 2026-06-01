from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Hyperdress.AI"
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = "data/hyperdress.db"
    hyperliquid_info_url: str = "https://api.hyperliquid.xyz/info"
    monitor_interval_seconds: int = Field(default=15, ge=5, le=3600)
    liquidation_alert_percent: float = Field(default=12.0, ge=1.0, le=80.0)
    position_change_alert_percent: float = Field(default=25.0, ge=1.0, le=500.0)
    alert_cooldown_seconds: int = Field(default=900, ge=0, le=86400)
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_proxy_url: str | None = None
    ai_provider: str = "none"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ai_proxy_url: str | None = None
    watched_wallets: list[str] = []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.replace("sqlite:///", "", 1))
        return Path(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
