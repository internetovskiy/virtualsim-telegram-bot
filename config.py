from typing import Any, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = ""
    ADMIN_IDS: List[int] = []
    VIRTUALSIM_API_KEY: str = ""
    VIRTUALSIM_BASE_URL: str = "https://virtualsim.io/api/v1"
    CRYPTOBOT_API_KEY: str = ""
    CRYPTOBOT_BASE_URL: str = "https://pay.crypt.bot/api"
    DATABASE_URL: str = "sqlite+aiosqlite:///bot.db"
    MIN_DEPOSIT: float = 1.0
    MAX_DEPOSIT: float = 1000.0
    BOT_MARKUP_PERCENT: float = 0.0
    CACHE_TTL: int = 300
    ACTIVATION_POLL_INTERVAL: int = 5
    ACTIVATION_TIMEOUT: int = 600

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def _admin_ids(cls, v: Any) -> List[int]:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, int):
            return [v]
        s = str(v).strip()
        if s.startswith("["):
            import json
            return [int(x) for x in json.loads(s)]
        return [int(x) for x in s.split(",") if str(x).strip().isdigit()]


settings = Settings()
