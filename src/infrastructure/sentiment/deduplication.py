"""
News headline deduplication engine.

Provides logic to detect and merge highly similar headlines from
different sources to prevent double-counting in sentiment aggregation.

Layer: Infrastructure
"""

from difflib import SequenceMatcher

from src.domain.ports.news_provider import RawHeadline


def deduplicate_headlines(
    headlines: list[RawHeadline], similarity_threshold: float = 0.85
) -> list[RawHeadline]:
    """Deduplicate a list of headlines based on title similarity.

    Args:
        headlines: List of RawHeadline objects.
        similarity_threshold: Float between 0 and 1. Headlines with a
                              title similarity ratio above this threshold
                              are considered duplicates.

    Returns:
        A new list of deduplicated RawHeadline objects. If duplicates are found,
        the first one is kept, and the 'source' string is updated to include
        the sources of the duplicates (e.g., 'Kontan, CNBC').
    """
    if not headlines:
        return []

    unique_headlines: list[RawHeadline] = []

    for new_headline in headlines:
        is_duplicate = False
        for i, existing_headline in enumerate(unique_headlines):
            # Check similarity ratio
            ratio = SequenceMatcher(
                None, new_headline.title.lower(), existing_headline.title.lower()
            ).ratio()

            if ratio >= similarity_threshold:
                # It's a duplicate.
                is_duplicate = True

                # Only append source if it's not already in the string (to avoid 'Kontan, Kontan')
                if new_headline.source not in existing_headline.source:
                    merged_source = f"{existing_headline.source}, {new_headline.source}"

                    # Create a new RawHeadline with the merged source
                    merged_headline = RawHeadline(
                        title=existing_headline.title,
                        source=merged_source,
                        published=existing_headline.published,  # Keep older timestamp
                        url=existing_headline.url,
                    )
                    unique_headlines[i] = merged_headline
                break

        if not is_duplicate:
            unique_headlines.append(new_headline)

    return unique_headlines
