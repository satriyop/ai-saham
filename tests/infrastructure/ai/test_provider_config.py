"""Tests for provider config resolution.

Layer: Infrastructure
"""


from src.infrastructure.ai.provider_config import resolve_ai_provider


def _make_config(provider: str):
    """Helper to build a fake config object with .ai.provider."""
    import types

    ai = types.SimpleNamespace(provider=provider)
    return types.SimpleNamespace(ai=ai)


class TestResolveAiProvider:
    """Provider precedence: explicit > env > app config."""

    def test_explicit_provider_wins_without_loading_app_config(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "claude")

        import src.infrastructure.ai.provider_config as pc

        original_load = pc.load_app_config
        called = False

        def raise_if_called():
            nonlocal called
            called = True
            raise RuntimeError("load_app_config should not be called")

        pc.load_app_config = raise_if_called
        try:
            result = resolve_ai_provider("OpenAI")
            assert result == "openai"
            assert not called, "load_app_config was called"
        finally:
            pc.load_app_config = original_load

    def test_env_provider_wins_without_loading_app_config(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "Gemini")

        import src.infrastructure.ai.provider_config as pc

        original_load = pc.load_app_config
        called = False

        def raise_if_called():
            nonlocal called
            called = True
            raise RuntimeError("load_app_config should not be called")

        pc.load_app_config = raise_if_called
        try:
            result = resolve_ai_provider(None)
            assert result == "gemini"
            assert not called, "load_app_config was called"
        finally:
            pc.load_app_config = original_load

    def test_empty_env_falls_back_to_app_config(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "")

        import src.infrastructure.ai.provider_config as pc

        original_load = pc.load_app_config
        try:
            pc.load_app_config = lambda: _make_config("DeepSeek")
            result = resolve_ai_provider(None)
            assert result == "deepseek"
        finally:
            pc.load_app_config = original_load

    def test_missing_env_falls_back_to_app_config(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)

        import src.infrastructure.ai.provider_config as pc

        original_load = pc.load_app_config
        try:
            pc.load_app_config = lambda: _make_config("Ollama")
            result = resolve_ai_provider(None)
            assert result == "ollama"
        finally:
            pc.load_app_config = original_load

    def test_empty_explicit_provider_does_not_fallback(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "claude")

        import src.infrastructure.ai.provider_config as pc

        original_load = pc.load_app_config
        called = False

        def raise_if_called():
            nonlocal called
            called = True
            raise RuntimeError("load_app_config should not be called")

        pc.load_app_config = raise_if_called
        try:
            result = resolve_ai_provider("")
            assert result == ""
            assert not called, "load_app_config was called"
        finally:
            pc.load_app_config = original_load
