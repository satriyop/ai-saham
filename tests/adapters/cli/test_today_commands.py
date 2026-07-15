"""Tests for the daily briefing CLI command."""

from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_cli_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "today" in result.stdout


def test_today_help_exits_zero():
    result = runner.invoke(app, ["today", "--help"])
    assert result.exit_code == 0
    assert "--universe" in result.stdout
    assert "--date" in result.stdout
    assert "--db" in result.stdout


def test_today_shows_market_source_tag(tmp_path: Path):
    from datetime import datetime
    from unittest.mock import patch

    from src.domain.value_objects.market_status import MarketStatus

    fake_status = MarketStatus(
        status="STATUS_OPEN",
        session_name="Regular",
        is_open=True,
        session_open="09:00",
        session_close="15:00",
        fetched_at=datetime.now(),
        source="test_source",
    )

    with patch(
        "src.infrastructure.browser.stockbit_market_time.get_display_market_status",
        return_value=fake_status,
    ):
        result = runner.invoke(
            app,
            [
                "today",
                "--universe",
                "lq45",
                "--db",
                str(tmp_path / "market.db"),
            ],
        )

    assert result.exit_code == 0
    assert "[test_source]" in result.stdout


def test_today_renders_rich_dashboard_with_lifecycle_next_steps(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "today",
            "--universe",
            "lq45",
            "--date",
            "2026-06-19",
            "--db",
            str(tmp_path / "market.db"),
        ],
    )

    assert result.exit_code == 0
    assert "Daily Briefing - 2026-06-19" in result.stdout
    assert "Data & Regime" in result.stdout
    assert "PRE-OPEN ASSESSMENT" in result.stdout
    assert "Top Accumulation Candidates" in result.stdout
    assert "Run: saham learn snapshot --force" in result.stdout
    stdout_clean = result.stdout.replace("\n", "").replace(" ", "").replace("│", "")
    assert "sahamscreenaccum--universelq45|sahamanalyzeswingTICKER" in stdout_clean


def test_today_uses_loaded_config_and_not_global(tmp_path: Path):
    from unittest.mock import MagicMock, patch

    from src.adapters.cli.today_commands import today

    with patch("src.adapters.cli.today_commands.load_accumulation_screener_config") as mock_load, \
         patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_cfg = MagicMock()
        mock_cfg.derived_features = MagicMock()
        mock_load.return_value = mock_cfg

        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_response = mock_uc.execute.return_value
        mock_response.universe = "lq45"
        mock_response.universe_count = 0
        mock_response.stale_count = 0
        mock_response.regime = None
        mock_response.opening_candidates = []
        mock_response.market_wide_opening_observations = []
        mock_response.accumulation_candidates = []
        mock_response.warnings = []
        mock_response.live_session_date = date(2026, 6, 19)
        mock_response.latest_completed_eod_date = date(2026, 6, 19)
        mock_response.opening_snapshot_date = date(2026, 6, 19)
        mock_response.is_historical = True
        mock_response.readiness_items = []
        mock_response.overall_authority = "READY"

        today(universe="lq45", date_str="2026-06-19", db_path=tmp_path / "market.db")

        mock_load.assert_called_once()


def test_today_historical_mode_output_and_suppression(tmp_path: Path):
    from unittest.mock import patch

    # Patch get_display_market_status to raise an exception.
    # It should NOT be called in historical mode.
    with patch(
        "src.infrastructure.browser.stockbit_market_time.get_display_market_status",
        side_effect=RuntimeError("Should not be called!"),
    ):
        result = runner.invoke(
            app,
            [
                "today",
                "--universe",
                "lq45",
                "--date",
                "2026-06-19",
                "--db",
                str(tmp_path / "market.db"),
            ],
        )

    assert result.exit_code == 0
    # Output must contain HISTORICAL and the summary rows
    assert "HISTORICAL — 2026-06-19" in result.stdout
    assert "Live session date" in result.stdout
    assert "Latest completed EOD" in result.stdout
    assert "Opening snapshot date" in result.stdout
    # Should not contain any live market status indications (since
    # get_display_market_status was not called/rendered)
    assert "Regular" not in result.stdout
    assert "⚠ open" not in result.stdout


def test_today_renders_data_readiness_table(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "today",
            "--universe",
            "lq45",
            "--date",
            "2026-06-19",
            "--db",
            str(tmp_path / "market.db"),
        ],
    )
    assert result.exit_code == 0
    assert "Data Readiness" in result.stdout
    assert "candles" in result.stdout
    assert "broker_flow" in result.stdout
    assert "market_context" in result.stdout
    assert "opening_snapshot" in result.stdout


def test_today_suppresses_accumulation_table_when_not_ready():
    from decimal import Decimal
    from unittest.mock import MagicMock, patch

    from src.application.dto.accumulation_screen import AccumulationCandidate
    from src.application.use_case.daily_briefing_use_case import (
        DailyBriefingResponse,
        DataReadiness,
    )

    fake_candidate = AccumulationCandidate(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("10000"),
        current_price=Decimal("10050"),
        vwap_discount_pct=0.5,
        rsi=50.0,
        trend="UP",
        foreign_flow_score=80.0,
        top_brokers=None,
        institutional_flag=True,
    )

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=None,
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=41,
        readiness_items=[
            DataReadiness(
                dataset="candles",
                required_as_of=date(2026, 6, 19),
                coverage_count=4,
                total_count=45,
                status="NOT_READY",
                reason="Only 4/45 tickers have current candle data",
            ),
            DataReadiness(
                dataset="broker_flow",
                required_as_of=date(2026, 6, 19),
                coverage_count=45,
                total_count=45,
                status="READY",
                reason=None,
            ),
            DataReadiness(
                dataset="market_context",
                required_as_of=date(2026, 6, 19),
                coverage_count=1,
                total_count=1,
                status="READY",
                reason=None,
            ),
            DataReadiness(
                dataset="opening_snapshot",
                required_as_of=date(2026, 6, 19),
                coverage_count=0,
                total_count=1,
                status="UNAVAILABLE",
                reason="Opening snapshot unavailable",
            )
        ],
        overall_authority="NOT_READY",
        regime=None,
        opening_candidates=[],
        accumulation_candidates=[fake_candidate],
        warnings=["Accumulation screen suppressed because data readiness is NOT_READY."],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "Suppressed" in result.stdout
        assert "NOT_READY" in result.stdout
        assert "BBCA" not in result.stdout


def test_today_marks_partial_accumulation_output():
    from decimal import Decimal
    from unittest.mock import MagicMock, patch

    from src.application.dto.accumulation_screen import AccumulationCandidate
    from src.application.use_case.daily_briefing_use_case import (
        DailyBriefingResponse,
        DataReadiness,
    )

    fake_candidate = AccumulationCandidate(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("10000"),
        current_price=Decimal("10050"),
        vwap_discount_pct=0.5,
        rsi=50.0,
        trend="UP",
        foreign_flow_score=80.0,
        top_brokers=None,
        institutional_flag=True,
    )

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=None,
        is_historical=True,
        universe="lq45",
        universe_count=10,
        data_freshness=[],
        stale_count=2,
        readiness_items=[
            DataReadiness(
                dataset="candles",
                required_as_of=date(2026, 6, 19),
                coverage_count=8,
                total_count=10,
                status="PARTIAL",
                reason="Only 8/10 tickers have current candle data",
            ),
            DataReadiness(
                dataset="broker_flow",
                required_as_of=date(2026, 6, 19),
                coverage_count=10,
                total_count=10,
                status="READY",
                reason=None,
            ),
            DataReadiness(
                dataset="market_context",
                required_as_of=date(2026, 6, 19),
                coverage_count=1,
                total_count=1,
                status="READY",
                reason=None,
            ),
            DataReadiness(
                dataset="opening_snapshot",
                required_as_of=date(2026, 6, 19),
                coverage_count=0,
                total_count=1,
                status="UNAVAILABLE",
                reason="Opening snapshot unavailable",
            )
        ],
        overall_authority="PARTIAL",
        regime=None,
        opening_candidates=[],
        accumulation_candidates=[fake_candidate],
        warnings=["Accumulation screen is shown with PARTIAL data readiness."],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "PARTIAL DATA" in result.stdout
        assert "BBCA" in result.stdout


def test_today_renders_market_wide_pre_open_observations_separately():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_briefing_use_case import (
        DailyBriefingResponse,
        OpeningBriefingCandidate,
    )

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=date(2026, 6, 19),
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=0,
        readiness_items=[],
        overall_authority="READY",
        regime=None,
        opening_candidates=[
            OpeningBriefingCandidate(
                ticker="A",
                opening_setup="PRIME",
                iev=1000,
                iep=1050,
                trend="UP",
            )
        ],
        market_wide_opening_observations=[
            OpeningBriefingCandidate(
                ticker="C",
                opening_setup="WATCH",
                iev=2000,
                iep=2050,
                trend="DOWN",
            )
        ],
        accumulation_candidates=[],
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "PRE-OPEN ASSESSMENT" in result.stdout
        assert "Market-wide observations" in result.stdout
        assert "A" in result.stdout
        assert "C" in result.stdout


def test_today_does_not_render_market_wide_ticker_in_universe_pre_open_table():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_briefing_use_case import (
        DailyBriefingResponse,
        OpeningBriefingCandidate,
    )

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=date(2026, 6, 19),
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=0,
        readiness_items=[],
        overall_authority="READY",
        regime=None,
        opening_candidates=[
            OpeningBriefingCandidate(
                ticker="A",
                opening_setup="PRIME",
                iev=1000,
                iep=1050,
                trend="UP",
            )
        ],
        market_wide_opening_observations=[
            OpeningBriefingCandidate(
                ticker="C",
                opening_setup="WATCH",
                iev=2000,
                iep=2050,
                trend="DOWN",
            )
        ],
        accumulation_candidates=[],
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0

        stdout = result.stdout
        idx_universe_title = stdout.index("PRE-OPEN ASSESSMENT")
        idx_market_wide_title = stdout.index("Market-wide observations")

        # Ticker C should not be rendered between universe title and market-wide title
        assert "│ C " not in stdout[idx_universe_title:idx_market_wide_title]
        # Ticker C should be rendered after market-wide title
        assert "│ C " in stdout[idx_market_wide_title:]


def test_today_pre_open_assessment_shows_no_actionable_when_only_skip():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_briefing_use_case import (
        DailyBriefingResponse,
        OpeningBriefingCandidate,
    )

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=date(2026, 6, 19),
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=0,
        readiness_items=[],
        overall_authority="READY",
        regime=None,
        opening_candidates=[
            OpeningBriefingCandidate(
                ticker="BBCA",
                opening_setup="SKIP",
                iev=10000,
                iep=10050,
                trend="UP",
            )
        ],
        market_wide_opening_observations=[],
        accumulation_candidates=[],
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "PRE-OPEN ASSESSMENT" in result.stdout
        assert "NO ACTIONABLE LQ45 SETUPS" in result.stdout
        assert "Universe observations" in result.stdout
        assert "BBCA" in result.stdout
        assert "Top Pre-Open Candidates" not in result.stdout


def test_today_pre_open_assessment_shows_actionable_rows_first():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_briefing_use_case import (
        DailyBriefingResponse,
        OpeningBriefingCandidate,
    )

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=date(2026, 6, 19),
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=0,
        readiness_items=[],
        overall_authority="READY",
        regime=None,
        opening_candidates=[
            OpeningBriefingCandidate(ticker="BBCA", opening_setup="PRIME"),
            OpeningBriefingCandidate(ticker="BBRI", opening_setup="SKIP"),
        ],
        market_wide_opening_observations=[],
        accumulation_candidates=[],
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0

        stdout = result.stdout
        idx_pre_open = stdout.index("PRE-OPEN ASSESSMENT")
        idx_actionable = stdout.index("ACTIONABLE LQ45 SETUPS")
        idx_bbca = stdout.index("BBCA")
        idx_observations = stdout.index("Universe observations")
        idx_bbri = stdout.index("BBRI")

        assert idx_pre_open < idx_actionable
        assert idx_actionable < idx_bbca
        assert idx_bbca < idx_observations
        assert idx_observations < idx_bbri


def test_today_pre_open_assessment_keeps_market_wide_separate():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_briefing_use_case import (
        DailyBriefingResponse,
        OpeningBriefingCandidate,
    )

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=date(2026, 6, 19),
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=0,
        readiness_items=[],
        overall_authority="READY",
        regime=None,
        opening_candidates=[
            OpeningBriefingCandidate(ticker="A", opening_setup="PRIME"),
        ],
        market_wide_opening_observations=[
            OpeningBriefingCandidate(ticker="C", opening_setup="WATCH"),
        ],
        accumulation_candidates=[],
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0

        stdout = result.stdout
        assert "Market-wide observations" in stdout
        idx_market_wide = stdout.index("Market-wide observations")
        idx_c = stdout.index("│ C ")

        assert idx_market_wide < idx_c

        idx_pre_open = stdout.index("PRE-OPEN ASSESSMENT")
        # C does not appear between PRE-OPEN ASSESSMENT and Market-wide observations
        assert "│ C " not in stdout[idx_pre_open:idx_market_wide]
