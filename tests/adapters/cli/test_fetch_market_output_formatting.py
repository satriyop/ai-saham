from datetime import date
from pathlib import Path

from src.adapters.cli.fetch_market_display import (
    clean_row_span,
    fmt_enrichment_column,
    fmt_inst_flow_column,
    fmt_meta_column,
    fmt_tracked_flow_column,
    print_table_summary,
    split_flow_parts,
)


def test_print_table_summary_does_not_truncate_impact(monkeypatch, tmp_path: Path, capsys):
    from src.application.use_case.data_update_status_use_case import DataUpdateTableStatus

    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_display.build_data_update_table_statuses",
        lambda **_: [
            DataUpdateTableStatus(
                table="foreign_flow_points",
                source="stockbit",
                rows=4532,
                tickers=44,
                range_label="2025-06-12..2026-06-17",
                status="partial",
                contains="Net foreign flow time series",
                impact="Some requested tickers are missing.",
                issue="foreign_flow_points has 44/45 requested tickers",
            )
        ],
    )

    print_table_summary(
        db_path=tmp_path / "data.db",
        stock_tickers=["BBCA"],
        candles_provider="yahoo",
        broker_provider_name="stockbit",
        no_meta=False,
        candles_only=False,
        broker_only=False,
        expected_trading_day=date(2026, 6, 17),
        enrichment_available=True,
    )

    output = capsys.readouterr().out
    assert "Some requested tickers are missing." in output
    assert "Some requested ti\n" not in output


def test_clean_row_span():
    assert clean_row_span("up-to-date(2026-06-19)") == "✓(2026-06-19)"
    assert clean_row_span("+26rows/span=84d") == "+26r(84d)"
    assert clean_row_span("backfill+90rows/span=260d") == "bf+90r(260d)"
    assert clean_row_span("refreshed/span=260d") == "ref(260d)"


def test_split_flow_parts():
    assert split_flow_parts("daily=✓(2026-06-19)") == ("daily=✓(2026-06-19)", "skip")
    assert split_flow_parts(
        "daily=✓(2026-06-19) agg=✓(2026-06-19)"
    ) == ("daily=✓(2026-06-19)", "agg=✓(2026-06-19)")
    assert split_flow_parts(
        "daily:+648rows/12codes/96d agg:+2rows/373d"
    ) == ("daily:+648rows/12codes/96d", "agg:+2rows/373d")
    assert split_flow_parts("skip") == ("skip", "skip")
    assert split_flow_parts("ERR:auth") == ("ERR:auth", "ERR:auth")


def test_fmt_tracked_flow_column():
    assert fmt_tracked_flow_column("daily=✓(2026-06-19)") == "✓(06-19)"
    assert fmt_tracked_flow_column("daily:+648rows/12codes/96d") == "+648r(96d)"
    assert fmt_tracked_flow_column("skip") == "skip"


def test_fmt_inst_flow_column():
    assert fmt_inst_flow_column("agg=✓(2026-06-19)") == "✓(06-19)"
    assert fmt_inst_flow_column("agg:+2rows/373d") == "+2r(373d)"
    assert fmt_inst_flow_column("skip") == "skip"


def test_fmt_meta_column():
    assert fmt_meta_column("cached(5d)") == "cached(5d)"
    assert fmt_meta_column("new(Financial Services)") == "new(Financial S..)"
    assert fmt_meta_column("skip") == "skip"


def test_fmt_enrichment_column():
    assert fmt_enrichment_column("skip") == "skip"
    assert fmt_enrichment_column(
        "✓(notation,analyst,insider,season,corp,holding,bandar,fundam,fwd_est,profile)"
    ) == "10/10 ✓"
    assert fmt_enrichment_column(
        "notation+analyst  ✓(insider,season,corp,holding,bandar,fundam,fwd_est,profile)"
    ) == "10/10 (+2: notation, analyst)"
    assert fmt_enrichment_column(
        "notation+analyst+insider  ✓(season,corp,holding,bandar,fundam,fwd_est,profile)"
    ) == "10/10 (+3)"
    assert fmt_enrichment_column(
        "ERR:insider:Playwright error,corp:timeout"
    ) == "8/10 (ERR: insider, corp)"
