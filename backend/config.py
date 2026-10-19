from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration from environment variables / `.env` (see `.env.example`)."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: str = ""
    llm_model: str = ""
    embed_model: str = ""
    concurrency: int = 8
    mock_llm: bool = True
    base_rate_hint: bool = False
    demo_mode: bool = False
    data_dir: str = "data"
    frontend_dist: str = "frontend/dist"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
