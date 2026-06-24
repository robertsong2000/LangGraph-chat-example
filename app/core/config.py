"""Configuration for the multi-agent chat application."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass
class Settings:
    """Runtime settings, sourced from environment variables."""

    # Model / provider
    model_name: str = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")
    api_key: str | None = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    api_base: str | None = os.getenv("API_BASE")
    temperature: float = float(os.getenv("TEMPERATURE", "0.7"))

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # Which agents are available (names)
    enabled_agents: tuple = ("supervisor", "coder", "researcher", "writer")

    # Whether to allow a local mock model when no API key is present
    use_mock_if_no_key: bool = True

    # SQLite checkpointer path (None = in-memory)
    sqlite_path: str | None = os.getenv("SQLITE_PATH", "./chat_checkpoints.db")

    @property
    def can_use_real_llm(self) -> bool:
        return bool(self.api_key)


settings = Settings()
