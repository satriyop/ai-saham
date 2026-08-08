from decimal import Decimal

import pytest

from src.application.services.accumulation_price_contract import (
    parse_canonical_positive_decimal_text,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100", Decimal("100")),
        ("100.0", Decimal("100.0")),
        ("1.00", Decimal("1.00")),
        ("0.1", Decimal("0.1")),
        ("1E+3", Decimal("1E+3")),
    ],
)
def test_parse_canonical_positive_decimal_text_accepts_writer_spellings(
    raw: str,
    expected: Decimal,
) -> None:
    assert parse_canonical_positive_decimal_text(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        True,
        100,
        100.0,
        "",
        " 100",
        "100 ",
        "+100",
        "0100",
        ".1",
        "1.",
        "1e3",
        "1E3",
        "0",
        "0.0",
        "-0",
        "-1",
        "NaN",
        "Infinity",
    ],
)
def test_parse_canonical_positive_decimal_text_rejects_non_writer_aliases(
    raw: object,
) -> None:
    assert parse_canonical_positive_decimal_text(raw) is None
