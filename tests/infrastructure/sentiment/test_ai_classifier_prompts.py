from src.infrastructure.sentiment.ai_classifier_prompts import USER_PROMPT, build_user_prompt


def test_build_user_prompt_matches_template():
    result = build_user_prompt("BBCA", "headline")
    assert result == USER_PROMPT.format(ticker="BBCA", headline="headline")


def test_build_user_prompt_preserves_long_headline_text():
    long_headline = "x" * 1000
    result = build_user_prompt("BBCA", long_headline)
    assert result == USER_PROMPT.format(ticker="BBCA", headline=long_headline)
