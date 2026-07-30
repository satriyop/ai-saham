"""Contract tests: sector-macro live series exclude known-dead Yahoo symbols.

Documents Track DQ-1 smoke decisions (2026-07): keep COAL ETF and CPO=F with
honest limits; never auto-map MTF=F / KO=F. Full narrative lives in
docs/data_sources.md § Sector macro series quality.
"""

from src.infrastructure.config.sector_macro_context_config_loader import (
    create_sector_macro_context_evidence_builder,
    load_sector_macro_context_config,
    required_sector_macro_series_tickers,
)


def test_dead_yahoo_symbols_not_in_live_required_series():
    series = required_sector_macro_series_tickers()
    assert "MTF=F" not in series
    assert "KO=F" not in series


def test_dead_symbols_not_referenced_by_any_live_map_factor():
    cfg = load_sector_macro_context_config()
    live_series = set()
    for refs in cfg.sector_maps.values():
        for ref in refs:
            entry = cfg.factor_library[ref.ref]
            if entry.kind == "return_sessions":
                live_series.add(entry.series)
    assert "MTF=F" not in live_series
    assert "KO=F" not in live_series


def test_coal_proxy_is_coal_etf_not_newcastle_future():
    cfg = load_sector_macro_context_config()
    assert cfg.factor_library["coal_proxy"].series == "COAL"
    coal_refs = [r.ref for r in cfg.sector_maps["coal"]]
    assert "coal_proxy" in coal_refs


def test_plantation_cpo_series_is_cpo_f_not_soy_oil_or_legacy():
    """Palm stays CPO=F; ZL=F soy oil is a different complex (not auto-substituted)."""
    cfg = load_sector_macro_context_config()
    assert cfg.factor_library["cpo"].series == "CPO=F"
    plantation_series = {
        cfg.factor_library[r.ref].series
        for r in cfg.sector_maps["plantation"]
        if cfg.factor_library[r.ref].kind == "return_sessions"
    }
    assert "CPO=F" in plantation_series
    assert "ZL=F" not in plantation_series
    assert "KO=F" not in plantation_series
    # Library must not silently redefine cpo to a non-palm series.
    for name, entry in cfg.factor_library.items():
        if entry.series == "ZL=F":
            assert name != "cpo"


def test_liquid_cores_still_required_for_fetch():
    series = required_sector_macro_series_tickers()
    for required in ("CL=F", "IDR=X", "COAL", "CPO=F", "HG=F", "GC=F", "ZC=F", "ZS=F"):
        assert required in series, required


def test_builder_loads_documented_proxies():
    builder = create_sector_macro_context_evidence_builder()
    assert builder.config.factor_library["coal_proxy"].series == "COAL"
    assert builder.config.factor_library["cpo"].series == "CPO=F"
