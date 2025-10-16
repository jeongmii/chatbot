from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from typing import List, Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # OpenAI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.7

    # App
    database_url: str = "sqlite:///./chat.db"
    allowed_origins: List[str] = ["*"]


@lru_cache()
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
