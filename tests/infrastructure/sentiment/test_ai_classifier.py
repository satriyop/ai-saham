from src.domain.value_objects.sentiment import CatalystType, Sentiment
from src.infrastructure.sentiment.ai_classifier import AIClassifier


def test_explicit_provider_beats_env_and_config(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier._default_ai_provider", lambda: "claude"
    )
    classifier = AIClassifier(provider="ollama")
    assert classifier.classifier_name == "ai:ollama"


def test_env_provider_beats_config(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier._default_ai_provider", lambda: "claude"
    )
    classifier = AIClassifier()
    assert classifier.classifier_name == "ai:openai"


def test_config_provider_used_when_explicit_and_env_absent(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier._default_ai_provider", lambda: "claude"
    )
    classifier = AIClassifier()
    assert classifier.classifier_name == "ai:claude"


def test_client_created_once_and_reused(monkeypatch):
    calls = []

    def fake_create_client(provider, model):
        calls.append((provider, model))
        return object()

    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier.create_ai_classifier_client",
        fake_create_client,
    )
    classifier = AIClassifier(provider="ollama")
    client1 = classifier._get_client()
    client2 = classifier._get_client()

    assert client1 is client2
    assert len(calls) == 1


def test_classify_batch_preserves_order(monkeypatch):
    responses = iter(["POSITIVE | EARNINGS", "NEGATIVE | RUMOR", "neutral | general"])

    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier.create_ai_classifier_client",
        lambda provider, model: object(),
    )
    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier.call_ai_classifier_provider",
        lambda provider, client, prompt, model: next(responses),
    )

    classifier = AIClassifier(provider="ollama")
    results = classifier.classify_batch("BBCA", ["h1", "h2", "h3"])

    assert [r.sentiment for r in results] == [
        Sentiment.POSITIVE,
        Sentiment.NEGATIVE,
        Sentiment.NEUTRAL,
    ]
    assert [r.catalyst for r in results] == [
        CatalystType.EARNINGS,
        CatalystType.RUMOR,
        CatalystType.GENERAL,
    ]


def test_provider_call_exception_returns_neutral_general(monkeypatch):
    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier.create_ai_classifier_client",
        lambda provider, model: object(),
    )

    def raise_error(provider, client, prompt, model):
        raise RuntimeError("provider call failed")

    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier.call_ai_classifier_provider", raise_error
    )

    classifier = AIClassifier(provider="ollama")
    result = classifier.classify("BBCA", "some headline")

    assert result.sentiment == Sentiment.NEUTRAL
    assert result.catalyst == CatalystType.GENERAL


def test_unsupported_provider_falls_back_to_neutral_general():
    classifier = AIClassifier(provider="nonexistent")
    result = classifier.classify("BBCA", "some headline")

    assert result.sentiment == Sentiment.NEUTRAL
    assert result.catalyst == CatalystType.GENERAL


def test_long_headline_is_truncated_before_prompt_build(monkeypatch):
    captured_prompts = []

    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier.create_ai_classifier_client",
        lambda provider, model: object(),
    )

    def fake_call(provider, client, prompt, model):
        captured_prompts.append(prompt)
        return "NEUTRAL | GENERAL"

    monkeypatch.setattr(
        "src.infrastructure.sentiment.ai_classifier.call_ai_classifier_provider", fake_call
    )

    classifier = AIClassifier(provider="ollama")
    long_headline = "x" * 1000
    classifier.classify("BBCA", long_headline)

    assert len(captured_prompts) == 1
    assert ("x" * 500) in captured_prompts[0]
    assert ("x" * 501) not in captured_prompts[0]
