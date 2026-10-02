from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://echonote:echonote@localhost:5432/echonote"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000"]
    s3_endpoint_url: str | None = None
    s3_public_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "echonote"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    gnani_api_key: str = ""
    gnani_url: str = "https://api.vachana.ai/stt/v3"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    max_upload_bytes: int = Field(default=262144000, ge=1024, le=5368709120)
    max_duration_seconds: int = Field(default=14400, ge=120)
    max_attempts: int = Field(default=3, ge=1, le=10)
    stale_seconds: int = Field(default=900, ge=600)

    @field_validator("s3_endpoint_url", "s3_public_endpoint_url", mode="before")
    @classmethod
    def empty_endpoint(cls, value):
        return value or None

    # A shared review workspace, not a multi-tenant service. Put behind access control.
    repository_url: str = ""


@lru_cache
def settings() -> Settings:
    return Settings()
