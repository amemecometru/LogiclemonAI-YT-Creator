"""Configuration for LogiclemonAI - Content Creator Pipeline."""

import os
from typing import Dict, Any, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    app_name: str = "LogiclemonAI - Content Creator"
    app_version: str = "2.0.0"
    debug: bool = False
    
    # AI Configuration (OpenAI-compatible, including OpenRouter)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: Optional[str] = os.getenv("OPENAI_BASE_URL", None)
    
    # OpenRouter specific headers
    http_referer: str = os.getenv("HTTP_REFERER", "")
    x_title: str = os.getenv("X_TITLE", "LogiclemonAI")
    
    # Supabase Configuration
    supabase_url: str = os.getenv("PUBLIC_SUPABASE_URL", "")
    supabase_anon_key: str = os.getenv("PUBLIC_SUPABASE_ANON_KEY", "")
    
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
    """Get configuration for AI agents."""
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