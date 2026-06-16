import os
from typing import Dict, Any, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "LogiclemonAI - Content Creator"
    app_version: str = "2.0.0"
    debug: bool = False
    # Comma-separated allowed CORS origins. "*" = allow all (credentials are then disabled per the CORS spec).
    cors_allow_origins: str = os.getenv("CORS_ALLOW_ORIGINS", "*")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: Optional[str] = os.getenv("OPENAI_BASE_URL", None)

    http_referer: str = os.getenv("HTTP_REFERER", "")
    x_title: str = os.getenv("X_TITLE", "LogiclemonAI")

    cloudflare_db_url: str = os.getenv("CLOUDFLARE_DB_URL", "")
    cloudflare_research_url: str = os.getenv("CLOUDFLARE_RESEARCH_URL", "")
    cloudflare_api_token: str = os.getenv("CLOUDFLARE_API_TOKEN", "")

    # X (Twitter) auto-thread worker — see workers/x-worker
    x_worker_url: str = os.getenv("X_WORKER_URL", "")        # e.g. https://logiclemonai-x.<sub>.workers.dev
    x_worker_token: str = os.getenv("X_WORKER_TOKEN", "")    # = the x-worker's API_TOKEN (gates POST /x/post)

    rate_limit_requests: int = 10
    rate_limit_window: int = 3600
    max_content_length: int = 5000
    default_quality_threshold: float = 0.7

    database_url: str = ""
    redis_url: str = ""

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }


settings = Settings()


def get_agent_config() -> Dict[str, Any]:
    config = {
        "openai_api_key": settings.openai_api_key,
        "model": settings.openai_model,
        "max_tokens": 4000,
        "temperature": 0.7,
        "timeout": 120
    }
    if settings.openai_base_url:
        config["base_url"] = settings.openai_base_url
    if settings.http_referer:
        config["default_headers"] = {
            "HTTP-Referer": settings.http_referer,
            "X-Title": settings.x_title,
        }
    return config
