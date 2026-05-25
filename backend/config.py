"""
Configuration Management Module
================================
All configuration is loaded from environment variables via pydantic-settings.
No hardcoded values anywhere in the codebase.

Reference: PRD Section 6.1 (config.py), Section 18.1 (Environment Variables)
"""

from __future__ import annotations

import json
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application-wide configuration loaded exclusively from environment
    variables. Every tuneable parameter in the system is defined here.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ────────────────────────────────────────────────────────────
    gemini_api_key: str = "your_key_here"
    llm_model: str = "gemini-3.0-flash"

    # ── Backend ────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    max_file_size_mb: int = 50
    fk_overlap_threshold: float = 0.5

    # ── Conversation Memory ────────────────────────────────────────────
    conversation_window_size: int = 5

    # ── Logging ────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── CORS ───────────────────────────────────────────────────────────
    cors_origins: List[str] = ["http://localhost:3000"]

    @property
    def max_file_size_bytes(self) -> int:
        """Convert MB limit to bytes for comparison during upload validation."""
        return self.max_file_size_mb * 1024 * 1024


# ── Singleton ──────────────────────────────────────────────────────────
# Instantiated once at import time; all modules import this instance.
settings = Settings()
