"""
Prompt templates for the AI headline classifier.

Layer: Infrastructure
"""

SYSTEM_PROMPT = """You are a financial news sentiment and catalyst classifier for Indonesian stocks.
Your task is to classify headlines as follows:

1. Sentiment: POSITIVE, NEUTRAL, or NEGATIVE.
2. Catalyst: EARNINGS, CORP_ACTION, REGULATORY, MACRO, GOVERNANCE, RUMOR, or GENERAL.

Classification guidelines for Catalysts:
- EARNINGS: Quarterly reports, profit projections, dividend news.
- CORP_ACTION: Stock splits, rights issues, buybacks, mergers, acquisitions.
- REGULATORY: Government policy, export bans, OJK/IDX mandates, legal cases.
- MACRO: Interest rates, global markets, commodity prices (Coal, Nickel, etc.).
- GOVERNANCE: Management changes, scandals, audits, ownership shifts.
- RUMOR: Unverified news, market gossip, speculative whispers.
- GENERAL: News that doesn't fit specific categories above.

Only respond in the format: SENTIMENT | CATALYST
Example: POSITIVE | EARNINGS
Example: NEGATIVE | RUMOR
No explanation or additional text."""

USER_PROMPT = (
    "Classify the sentiment of this headline STRICTLY in relation to the "
    "company represented by ticker '{ticker}'.\n\nHeadline: {headline}"
)


def build_user_prompt(ticker: str, headline: str) -> str:
    """Build the user prompt for a given ticker and headline."""
    return USER_PROMPT.format(ticker=ticker, headline=headline)
