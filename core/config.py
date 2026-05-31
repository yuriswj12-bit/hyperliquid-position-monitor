from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    poll_interval_seconds: int = 25
    min_notional_usd_large: float = 1_000_000

    class Config:
        env_file = ".env"