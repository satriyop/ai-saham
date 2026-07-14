import sys
import types

import pytest

from src.domain.ports.headline_classifier import HeadlineClassifierError
from src.infrastructure.sentiment import ai_classifier_providers as providers


def test_create_client_unsupported_provider_raises():
    with pytest.raises(HeadlineClassifierError, match="Unsupported AI provider"):
        providers.create_ai_classifier_client("nonexistent")


def test_call_provider_unsupported_provider_raises():
    with pytest.raises(HeadlineClassifierError, match="Unsupported provider"):
        providers.call_ai_classifier_provider("nonexistent", client=None, user_prompt="hi")


def test_create_deepseek_client_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = lambda **kwargs: object()
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    with pytest.raises(HeadlineClassifierError, match="DEEPSEEK_API_KEY not set"):
        providers.create_ai_classifier_client("deepseek")


def test_create_claude_client_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_anthropic = types.ModuleType("anthropic")
    fake_anthropic.Anthropic = lambda **kwargs: object()
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    with pytest.raises(HeadlineClassifierError, match="ANTHROPIC_API_KEY not set"):
        providers.create_ai_classifier_client("claude")


def test_create_openai_client_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = lambda **kwargs: object()
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    with pytest.raises(HeadlineClassifierError, match="OPENAI_API_KEY not set"):
        providers.create_ai_classifier_client("openai")


def test_create_gemini_client_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    fake_genai = types.ModuleType("google.generativeai")
    fake_genai.configure = lambda **kwargs: None
    fake_genai.GenerativeModel = lambda model: object()
    fake_google = types.ModuleType("google")
    fake_google.generativeai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

    with pytest.raises(HeadlineClassifierError, match="GOOGLE_API_KEY not set"):
        providers.create_ai_classifier_client("gemini")


def test_create_ollama_client_uses_fake_sdk_no_network(monkeypatch):
    fake_ollama = types.ModuleType("ollama")
    fake_ollama.chat = lambda **kwargs: {"message": {"content": "POSITIVE | EARNINGS"}}
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    client = providers.create_ai_classifier_client("ollama")

    assert client["model"] == "llama3.2"
    result = providers.call_ai_classifier_provider("ollama", client, "hello")
    assert result == "POSITIVE | EARNINGS"


def test_client_factory_class_delegates_to_function(monkeypatch):
    fake_ollama = types.ModuleType("ollama")
    fake_ollama.chat = lambda **kwargs: {"message": {"content": "ok"}}
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)

    client = providers.AIClassifierProviderClientFactory.create("ollama", model="custom-model")

    assert client["model"] == "custom-model"
