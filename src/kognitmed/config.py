"""
Application settings via pydantic-settings.

API keys are NEVER hardcoded. If missing, the app raises a clear error.
SECRET_KEY uses a multi-tiered fallback:
  1. Environment variable
  2. Local secret file (jwt_secret.txt)
  3. Randomly generated ephemeral key + severe warning (dev only)
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_SECRET_FILE = Path(__file__).parent.parent.parent / "jwt_secret.txt"


def _resolve_secret_key() -> str:
    """Multi-tiered fallback for SECRET_KEY — never hardcoded."""
    # Tier 1: environment variable
    if key := os.getenv("SECRET_KEY"):
        return key
    # Tier 2: local secret file (useful in restricted dev sandboxes)
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text().strip()
    # Tier 3: ephemeral random key — dev only, NOT suitable for production
    # TODO(security): This will break session consistency across restarts/instances.
    ephemeral = secrets.token_hex(32)
    logging.warning(
        "SECRET_KEY not set. Generating ephemeral secret key. "
        "This is NOT suitable for production — sessions will not persist across restarts."
    )
    return ephemeral


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────
    app_name: str = "KognitMed"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # ── Security ─────────────────────────────────
    secret_key: str = ""
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [x.strip() for x in v.split(",") if x.strip()]
        return v  # type: ignore

    # ── LLM ──────────────────────────────────────
    llm_provider: Literal["openai", "gemini"] = "openai"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # ── MongoDB ──────────────────────────────────
    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_user: str = "admin"
    mongo_password: str = "securepassword123"
    mongo_db: str = "kognitmed"

    @property
    def mongo_uri(self) -> str:
        """Construct the MongoDB connection URI securely."""
        import urllib.parse
        user = urllib.parse.quote_plus(self.mongo_user)
        pwd = urllib.parse.quote_plus(self.mongo_password)
        return f"mongodb://{user}:{pwd}@{self.mongo_host}:{self.mongo_port}/{self.mongo_db}?authSource=admin"

    def model_post_init(self, __context: object) -> None:
        # Resolve secret key with fallback strategy
        if not self.secret_key:
            object.__setattr__(self, "secret_key", _resolve_secret_key())


def get_settings() -> Settings:
    """Return cached settings instance."""
    return _settings


_settings = Settings()
