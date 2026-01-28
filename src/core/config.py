# src/core/config.py
from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    base_url: str = Field(default="http://localhost:1236/v1", alias="LLM_BASE_URL")
    model: str = Field(default="", alias="LLM_MODEL")
    temperature: float = Field(default=0.7, alias="LLM_TEMPERATURE")
    max_tokens: int = Field(default=1000, alias="LLM_MAX_TOKENS")
    timeout: int = Field(default=30, alias="LLM_TIMEOUT")
    max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="chat-workflow", alias="APP_NAME")
    env: str = Field(default="local", alias="ENV")

    db_url: str = Field(..., alias="DB_URL")

    llm: LLMSettings = LLMSettings()


settings = Settings()
