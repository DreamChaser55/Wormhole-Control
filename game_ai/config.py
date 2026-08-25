"""Secret-safe runtime configuration for the OpenAI adapter."""

from __future__ import annotations

import os
from pathlib import Path


class AIConfigurationError(RuntimeError):
    pass


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_openai_api_key() -> str:
    """Load a key without logging or persisting it.

    Environment configuration takes precedence. The repository-local fallback
    exists for this desktop project and is protected by the repository's key
    file ignore rule.
    """
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if not value:
        key_path = repository_root() / "API_keys" / "OpenAI.key"
        try:
            value = key_path.read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
    if not value:
        raise AIConfigurationError(
            "No OpenAI API key is configured. Set OPENAI_API_KEY or add "
            "API_keys/OpenAI.key."
        )
    if len(value) < 20 or any(character.isspace() for character in value):
        raise AIConfigurationError("The configured OpenAI API key is malformed.")
    return value
