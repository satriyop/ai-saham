from datetime import datetime
from src.infrastructure.browser.stockbit_fundamentals import _parse_fundamentals, _parse_market_cap
from src.domain.value_objects.company_fundamentals import CompanyFundamentals

def test_parse_market_cap():
    assert _parse_market_cap("755,060 B") == 755_060_000_000_000
    assert _parse_market_cap("12.5 T") == 12_500_000_000_000
    assert _parse_market_cap("500 M") == 500_000_000
    assert _parse_market_cap("  12,345  ") == 12345
    assert _parse_market_cap(None) is None
    assert _parse_market_cap("-") is None

def test_parse_fundamentals_new_schema():
    body = {
        "data": {
            "closure_fin_items_results": [
                {
                    "fin_name_results": [
                        {
                            "fitem": {
                                "id": "2891",
                                "name": "Current PE Ratio (TTM)",
                                "value": "13.00"
                            }
                        },
                        {
                            "fitem": {
                                "id": "2896",
                                "name": "Current Price to Book Value",
                                "value": "2.91"
                            }
                        },
                        {
                            "fitem": {
                                "id": "13200",
                                "name": "Current EPS (TTM)",
                                "value": "471.10"
                            }
                        }
                    ],
                    "keystats_name": "Current Valuation"
                }
            ],
            "stats": {
                "current_share_outstanding": "123.28 B",
                "market_cap": "755,060 B",
                "enterprise_value": "731,555 B",
                "free_float": "42.46%"
            },
            "info": ""
        }
    }
    
    result = _parse_fundamentals("BBCA", body)
    assert result is not None
    assert result.ticker == "BBCA"
    assert result.pe_ratio_ttm == 13.00
    assert result.pbv == 2.91
    assert result.market_cap_idr == 755_060_000_000_000

def test_parse_fundamentals_legacy_schema():
    body = {
        "data": {
            "closure_fin_items_results": [
                {
                    "fin_name_results": [
                        {
                            "fitem": {
                                "id": "2891",
                                "name": "Current PE Ratio (TTM)",
                                "value": "13.00"
                            }
                        }
                    ]
                }
            ],
            "info": {
                "market_cap": {"raw": "776634150000000"},
                "pbv": {"raw": "3.1"}
            }
        }
    }
    
    result = _parse_fundamentals("BBCA", body)
    assert result is not None
    assert result.ticker == "BBCA"
    assert result.pe_ratio_ttm == 13.00
    # Since stats is missing, market_cap is None in new logic unless info fallback is used
    # (The code currently falls back for PBV, but not for market_cap since the legacy JSON structure is deprecated)
    assert result.pbv == 3.1
