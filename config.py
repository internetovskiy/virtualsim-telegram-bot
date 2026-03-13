from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    BOT_TOKEN: str = " "
    ADMIN_IDS: List[int] = [123456]
    
    VIRTUALSIM_API_KEY: str = " "
    VIRTUALSIM_BASE_URL: str = "https://virtualsim.io/api/v1"
    
    CRYPTOBOT_API_KEY: str = " "
    CRYPTOBOT_BASE_URL: str = "https://pay.crypt.bot/api"
    
    DATABASE_URL: str = "sqlite+aiosqlite:///bot.db"
    
    MIN_DEPOSIT: float = 1.0
    MAX_DEPOSIT: float = 1000.0
    
    CACHE_TTL: int = 300
    ACTIVATION_POLL_INTERVAL: int = 5
    ACTIVATION_TIMEOUT: int = 600
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
