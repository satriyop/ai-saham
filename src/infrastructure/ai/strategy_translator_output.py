"""
YAML output canonicalization for strategy translation.

Layer: Infrastructure
"""

import re


def canonicalize_yaml(raw: str) -> str:
    """Normalize YAML output from LLM.

    - Strip leading/trailing whitespace
    - Remove markdown code blocks
    - Handle common LLM quirks

    Args:
        raw: Raw LLM output string.

    Returns:
        Canonicalized YAML string or "UNSUPPORTED".

    Example:
        >>> canonicalize_yaml("```yaml\\nversion: 1\\n```")
        'version: 1'
        >>> canonicalize_yaml("UNSUPPORTED - cannot translate")
        'UNSUPPORTED'
    """
    # Strip whitespace
    result = raw.strip()

    # Remove markdown code blocks (yaml, yml, or plain)
    result = re.sub(r"^```(?:ya?ml)?\s*\n?", "", result)
    result = re.sub(r"\n?```\s*$", "", result)
    result = result.strip()

    if not result:
        return "UNSUPPORTED"

    # Check for UNSUPPORTED (case-insensitive, with any suffix)
    if result.upper().startswith("UNSUPPORTED"):
        return "UNSUPPORTED"

    return result
