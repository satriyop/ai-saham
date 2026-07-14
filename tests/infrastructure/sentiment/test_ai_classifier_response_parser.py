import pytest

from src.domain.value_objects.sentiment import CatalystType, Sentiment
from src.infrastructure.sentiment.ai_classifier_response_parser import (
    parse_ai_classification_response,
)


@pytest.mark.parametrize(
    "response, expected_sentiment, expected_catalyst",
    [
        ("POSITIVE | EARNINGS", Sentiment.POSITIVE, CatalystType.EARNINGS),
        ("NEGATIVE | RUMOR", Sentiment.NEGATIVE, CatalystType.RUMOR),
        ("neutral | general", Sentiment.NEUTRAL, CatalystType.GENERAL),
        ("POSITIVE", Sentiment.POSITIVE, CatalystType.GENERAL),
        ("something unclear", Sentiment.NEUTRAL, CatalystType.GENERAL),
        ("POSITIVE | UNKNOWN", Sentiment.POSITIVE, CatalystType.GENERAL),
        ("NEGATIVE | GOVERNANCE extra words", Sentiment.NEGATIVE, CatalystType.GOVERNANCE),
    ],
)
def test_parse_ai_classification_response(response, expected_sentiment, expected_catalyst):
    result = parse_ai_classification_response(response)
    assert result.sentiment == expected_sentiment
    assert result.catalyst == expected_catalyst
