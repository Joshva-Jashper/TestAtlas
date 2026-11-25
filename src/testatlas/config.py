from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TESTATLAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "TestAtlas"
    environment: Literal["development", "test", "staging", "production"] = "development"
    github_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    github_total_timeout_seconds: float = Field(default=30.0, gt=0, le=90)
    github_user_agent: str = "TestAtlas/0.1.0"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
