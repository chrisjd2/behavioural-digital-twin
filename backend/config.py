from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.arms import LLMOptions


class Settings(BaseSettings):
    """App configuration from environment variables / `.env` (see `.env.example`)."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: str = ""
    llm_model: str = ""
    # Gemini Flash thinks by default; pin the level explicitly (decided on the dev set, #15).
    llm_reasoning_effort: Literal["none", "low", "medium", "high"] = "medium"
    llm_max_output_tokens: int = 4096
    embed_model: str = ""
    embed_dimensions: int = 768  # Gemini embeddings accept a reduced output size
    concurrency: int = 8
    mock_llm: bool = True
    base_rate_hint: bool = False
    demo_mode: bool = False
    data_dir: str = "data"
    hf_token: str = ""
    frontend_dist: str = "frontend/dist"
    hook_config: str = "config/hook.json"  # Step 0's dev-set example (scripts.pick_hook)

    def llm_options(self) -> LLMOptions:
        return LLMOptions(
            reasoning_effort=self.llm_reasoning_effort,
            max_output_tokens=self.llm_max_output_tokens,
            base_rate_hint=self.base_rate_hint,
            embed_model=self.embed_model,
            embed_dimensions=self.embed_dimensions,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
