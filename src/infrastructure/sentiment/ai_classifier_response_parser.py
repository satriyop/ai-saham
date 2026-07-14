"""
Response parsing for the AI headline classifier.

Layer: Infrastructure
"""

from src.domain.value_objects.sentiment import CatalystType, Classification, Sentiment


def parse_ai_classification_response(response: str) -> Classification:
    """Parse AI response to Classification.

    Args:
        response: Raw AI response text (expected: SENTIMENT | CATALYST)

    Returns:
        Parsed Classification (defaults to NEUTRAL|GENERAL on ambiguity)
    """
    response = response.strip().upper()

    sentiment = Sentiment.NEUTRAL
    if "POSITIVE" in response:
        sentiment = Sentiment.POSITIVE
    elif "NEGATIVE" in response:
        sentiment = Sentiment.NEGATIVE

    catalyst = CatalystType.GENERAL
    if "|" in response:
        cat_part = response.split("|")[1].strip()
        for ct in CatalystType:
            if ct.name in cat_part:
                catalyst = ct
                break

    return Classification(sentiment=sentiment, catalyst=catalyst)
