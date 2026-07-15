"""AI provider name resolution.

Layer: Infrastructure
"""

from __future__ import annotations

import os

from src.infrastructure.config.app_config import load_app_config


def resolve_ai_provider(explicit_provider: str | None = None) -> str:
    """Resolve AI provider name from explicit arg, env, then app config.

    Precedence:
    1. explicit_provider when not None
    2. AI_PROVIDER environment variable when set/non-empty
    3. load_app_config().ai.provider

    Returns lowercase provider name.
    """
    if explicit_provider is not None:
        return explicit_provider.lower()

    env_provider = os.getenv("AI_PROVIDER")
    if env_provider:
        return env_provider.lower()

    return load_app_config().ai.provider.lower()
