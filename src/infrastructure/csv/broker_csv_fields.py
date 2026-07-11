"""
Shared CSV field parsing utilities for broker data.

Provides header mapping and primitive value parsing used by both
simple and detailed format parsers.

Layer: Infrastructure
Dependencies: Domain ports and entities only
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from src.domain.entities.broker_flow import BrokerType
from src.domain.ports.csv_broker_parser import ColumnMapping, Transform


def build_header_map(
    csv_headers: list[str],
    mapping: ColumnMapping,
) -> dict[str, str]:
    """
    Build mapping from field names to actual CSV column names.

    Handles case-insensitive matching and common variations
    (spaces, dashes, underscores).

    Args:
        csv_headers: Actual column headers from CSV file
        mapping: Configured column name mappings

    Returns:
        Dict mapping field names to CSV column names
    """
    header_map = {}

    # Normalize CSV headers for matching
    normalized_csv = {}
    for h in csv_headers:
        norm = h.strip().lower().replace(" ", "_").replace("-", "_")
        normalized_csv[norm] = h

    # Map each field to its CSV column
    field_mappings = {
        "date": mapping.date,
        "ticker": mapping.ticker,
        "foreign_buy_value": mapping.foreign_buy_value,
        "foreign_sell_value": mapping.foreign_sell_value,
        "foreign_buy_lot": mapping.foreign_buy_lot,
        "foreign_sell_lot": mapping.foreign_sell_lot,
        "total_value": mapping.total_value,
        "total_lot": mapping.total_lot,
        "broker_code": mapping.broker_code,
        "broker_name": mapping.broker_name,
        "broker_type": mapping.broker_type,
        "buy_lot": mapping.buy_lot,
        "sell_lot": mapping.sell_lot,
        "buy_value": mapping.buy_value,
        "sell_value": mapping.sell_value,
    }

    for field, column_name in field_mappings.items():
        norm_col = column_name.lower().replace(" ", "_").replace("-", "_")
        if norm_col in normalized_csv:
            header_map[field] = normalized_csv[norm_col]
        elif column_name in csv_headers:
            # Exact match fallback
            header_map[field] = column_name

    return header_map


def parse_csv_date(value: str, transform: Transform | None) -> date:
    """
    Parse date string with optional format transform.

    Supported formats (tried in order if no transform):
    - YYYY-MM-DD (ISO)
    - DD/MM/YYYY
    - MM/DD/YYYY
    - DD-MM-YYYY
    - YYYYMMDD

    Args:
        value: Date string to parse
        transform: Optional Transform with date_format

    Returns:
        datetime.date object

    Raises:
        ValueError: If date cannot be parsed
    """
    if not value:
        raise ValueError("Empty date value")

    date_format = transform.date_format if transform else None

    if date_format:
        try:
            from datetime import datetime

            return datetime.strptime(value, date_format).date()
        except ValueError:
            raise ValueError(
                f"Invalid date '{value}' for format '{date_format}'"
            )

    # Try common formats
    formats = [
        "%Y-%m-%d",  # ISO format
        "%d/%m/%Y",  # DD/MM/YYYY
        "%m/%d/%Y",  # MM/DD/YYYY
        "%d-%m-%Y",  # DD-MM-YYYY
        "%Y%m%d",  # YYYYMMDD
    ]

    from datetime import datetime

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError(
        f"Could not parse date '{value}'. "
        f"Supported formats: YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY"
    )


def parse_csv_decimal(
    value: str,
    transform: Transform | None,
    default: Decimal = Decimal("0"),
) -> Decimal:
    """
    Parse decimal value with optional multiplier transform.

    Cleans value by removing commas, spaces, and 'Rp' currency symbol.

    Args:
        value: String value to parse
        transform: Optional Transform with multiplier
        default: Default value for empty/invalid input

    Returns:
        Parsed Decimal value
    """
    if not value:
        return default

    # Clean value: remove commas, spaces, currency symbols
    cleaned = value.replace(",", "").replace(" ", "").replace("Rp", "").strip()

    try:
        result = Decimal(cleaned)
    except InvalidOperation:
        return default

    # Apply multiplier if specified
    if transform and transform.multiplier:
        result *= transform.multiplier

    return result


def parse_csv_int(value: str, default: int = 0) -> int:
    """
    Parse integer value.

    Handles comma separators and float-formatted integers (e.g., "1000.0").

    Args:
        value: String value to parse
        default: Default value for empty/invalid input

    Returns:
        Parsed integer
    """
    if not value:
        return default

    cleaned = value.replace(",", "").replace(" ", "").strip()

    try:
        return int(float(cleaned))  # Handle "1000.0" format
    except ValueError:
        return default


def parse_broker_type(value: str) -> BrokerType:
    """
    Parse broker type from string.

    Accepted values (case-insensitive):
    - FOREIGN, ASING, F, A -> BrokerType.FOREIGN
    - LOCAL, LOKAL, L, D, DOMESTIC -> BrokerType.LOCAL
    - Anything else -> BrokerType.UNKNOWN

    Args:
        value: Broker type string

    Returns:
        BrokerType enum value
    """
    value_upper = value.upper()

    if value_upper in ("FOREIGN", "ASING", "F", "A"):
        return BrokerType.FOREIGN
    elif value_upper in ("LOCAL", "LOKAL", "L", "D", "DOMESTIC"):
        return BrokerType.LOCAL
    else:
        return BrokerType.UNKNOWN
