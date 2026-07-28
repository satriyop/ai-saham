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
                "--offline",
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
    assert "ACCUMULATION SCREEN" in result.stdout
    assert "Run: saham research pre-open capture" in result.stdout


def test_today_uses_loaded_config_and_not_global(tmp_path: Path):
    from unittest.mock import MagicMock, patch

    from src.adapters.cli.today_commands import today

    with (
        patch("src.adapters.cli.today_commands.load_accumulation_screener_config") as mock_load,
        patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class,
    ):
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
        mock_response.accumulation_summary = None
        mock_response.daily_accumulation_candidates = []
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
        accum_score=80.0,
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
            ),
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
    from src.application.use_case.daily_accumulation_projection import (
        DailyAccumulationCandidate,
        DailyAccumulationSummary,
    )
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
        accum_score=80.0,
        top_brokers=None,
        institutional_flag=True,
    )

    fake_projected_candidate = DailyAccumulationCandidate(
        ticker="BBCA",
        accum_score=80.0,
        setup_phase="ACCUMULATION",
        signal_score=70,
        signal_authority_coverage=0.8,
        risk_status="OPEN",
        action="WATCH",
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
            ),
        ],
        overall_authority="PARTIAL",
        regime=None,
        opening_candidates=[],
        accumulation_candidates=[fake_candidate],
        accumulation_summary=DailyAccumulationSummary(
            checked=10,
            data_ready=8,
            flow_candidates=1,
            enter_count=0,
            watch_count=1,
            blocked_count=0,
            unclassified_count=0,
        ),
        daily_accumulation_candidates=[fake_projected_candidate],
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
                opening_setup="ENTER",
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
                opening_setup="ENTER",
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
                opening_setup="AVOID",
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
            OpeningBriefingCandidate(ticker="BBCA", opening_setup="ENTER"),
            OpeningBriefingCandidate(ticker="BBRI", opening_setup="AVOID"),
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
            OpeningBriefingCandidate(ticker="A", opening_setup="ENTER"),
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


def test_today_accumulation_screen_renders_canonical_projection():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_accumulation_projection import (
        DailyAccumulationCandidate,
        DailyAccumulationSummary,
    )
    from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse

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
        opening_candidates=[],
        market_wide_opening_observations=[],
        accumulation_candidates=[],
        accumulation_summary=DailyAccumulationSummary(
            checked=45,
            data_ready=41,
            flow_candidates=1,
            enter_count=0,
            watch_count=1,
            blocked_count=0,
            unclassified_count=0,
        ),
        daily_accumulation_candidates=[
            DailyAccumulationCandidate(
                ticker="INDF",
                accum_score=60.6,
                setup_phase="ACCUMULATION",
                signal_score=72,
                signal_authority_coverage=0.82,
                risk_status="OPEN",
                action="WATCH",
            )
        ],
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0

        stdout = result.stdout
        assert "ACCUMULATION SCREEN" in stdout
        assert "Flow" in stdout
        assert "Phase" in stdout
        assert "Signal" in stdout
        assert "Coverage" in stdout
        assert "Risk" in stdout
        assert "Action" in stdout
        assert "INDF" in stdout
        assert "WATCH" in stdout
        assert "Top Accumulation Candidates" not in stdout


def test_today_accumulation_not_ready_suppresses_projection_rows():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_accumulation_projection import (
        DailyAccumulationCandidate,
    )
    from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=date(2026, 6, 19),
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=41,
        readiness_items=[],
        overall_authority="NOT_READY",
        regime=None,
        opening_candidates=[],
        market_wide_opening_observations=[],
        accumulation_candidates=[],
        accumulation_summary=None,
        # Simulates a use case bug that leaks rows even though NOT_READY; the
        # adapter must still suppress rendering regardless of this field.
        daily_accumulation_candidates=[
            DailyAccumulationCandidate(
                ticker="ZZZZ",
                accum_score=99.0,
                setup_phase="ACCUMULATION",
                signal_score=90,
                signal_authority_coverage=0.9,
                risk_status="OPEN",
                action="ENTER",
            )
        ],
        warnings=["Accumulation screen suppressed because data readiness is NOT_READY."],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "Suppressed" in result.stdout
        assert "ZZZZ" not in result.stdout


def test_market_regime_text_renders_all_fields():
    from src.adapters.cli.today_commands import _market_regime_text

    ctx = type(
        "C",
        (),
        {
            "regime": type("R", (), {"value": "RISK_ON"})(),
            "conviction": 0.69,
            "regime_confidence": 0.30,
            "regime_stability": "TRANSITIONING",
            "transition_warning": None,
        },
    )()

    expected = "RISK_ON | conviction 0.69 | confidence 0.30 | stability TRANSITIONING"
    assert _market_regime_text(ctx) == expected


def test_market_regime_text_omits_optional_metadata():
    from src.adapters.cli.today_commands import _market_regime_text

    ctx = type(
        "C",
        (),
        {
            "regime": type("R", (), {"value": "RISK_ON"})(),
            "conviction": 0.69,
            "regime_confidence": None,
            "regime_stability": None,
            "transition_warning": None,
        },
    )()

    assert _market_regime_text(ctx) == "RISK_ON | conviction 0.69"


def test_market_regime_text_appends_transition_warning():
    from src.adapters.cli.today_commands import _market_regime_text

    ctx = type(
        "C",
        (),
        {
            "regime": type("R", (), {"value": "RISK_ON"})(),
            "conviction": 0.69,
            "regime_confidence": None,
            "regime_stability": None,
            "transition_warning": "some warning",
        },
    )()

    assert _market_regime_text(ctx) == "RISK_ON | conviction 0.69 | transition: some warning"


def test_today_market_regime_renders_plain_values():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse

    fake_regime = type(
        "MC",
        (),
        {
            "regime": type("R", (), {"value": "RISK_ON"})(),
            "conviction": 0.69,
            "regime_confidence": 0.30,
            "regime_stability": "TRANSITIONING",
            "transition_warning": None,
            "factors": (),
        },
    )()

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=None,
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=0,
        readiness_items=[],
        overall_authority="READY",
        regime=fake_regime,
        opening_candidates=[],
        market_wide_opening_observations=[],
        accumulation_candidates=[],
        accumulation_summary=None,
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "RISK_ON" in result.stdout
        assert "conviction 0.69" in result.stdout
        assert "confidence 0.30" in result.stdout
        assert "BULLISH" not in result.stdout
        assert "(5/7)" not in result.stdout


def _render_to_text(render) -> str:
    from rich.console import Console, Group

    console = Console(width=200, record=True)
    console.print(Group(*render.elements))
    return console.export_text()


def test_setup_lens_impact_no_candidates_renders_exact_string():
    from src.adapters.cli.today_commands import _setup_lens_impact_elements

    text = _render_to_text(_setup_lens_impact_elements(None))
    assert "SETUP LENS IMPACT" in text
    assert "No accumulation candidates to evaluate." in text


def test_setup_lens_impact_empty_rows_renders_exact_string():
    from src.adapters.cli.today_commands import _setup_lens_impact_elements

    result = type("R", (), {"rows": ()})()
    text = _render_to_text(_setup_lens_impact_elements(result))
    assert "No accumulation candidates to evaluate." in text


def _cell(setup_name, action="WATCH", score=70, match="MATCH", capped=None, warning=None):
    return type(
        "Cell",
        (),
        {
            "setup_name": setup_name,
            "action": action,
            "signal_score": score,
            "setup_match": match,
            "entry_authority": True,
            "capped_reason": capped,
            "warning": warning,
        },
    )()


def test_setup_lens_impact_renders_all_four_columns_and_next_block():
    from src.adapters.cli.today_commands import _setup_lens_impact_elements
    from src.application.use_case.evaluate_swing_setup_use_case import (
        AVAILABLE_SWING_SETUPS,
    )

    cells = tuple(_cell(name, action="WATCH") for name in AVAILABLE_SWING_SETUPS)
    row = type("Row", (), {"ticker": "BBRI", "base_action": "WATCH", "cells": cells})()
    result = type("R", (), {"rows": (row,)})()

    text = _render_to_text(_setup_lens_impact_elements(result))

    for setup_name in AVAILABLE_SWING_SETUPS:
        assert setup_name in text
    # Next block includes actual ticker and setup name; never a literal placeholder.
    assert "Next:" in text
    assert f"saham plan swing BBRI --setup {AVAILABLE_SWING_SETUPS[0]}" in text
    assert "TICKER" not in text


def test_setup_lens_impact_capped_cell_shows_no_entry_suffix():
    from src.adapters.cli.today_commands import _setup_lens_impact_elements
    from src.application.use_case.evaluate_swing_setup_use_case import (
        AVAILABLE_SWING_SETUPS,
    )

    first = AVAILABLE_SWING_SETUPS[0]
    cells = (_cell(first, action="WATCH", capped="no standalone entry authority"),) + tuple(
        _cell(name) for name in AVAILABLE_SWING_SETUPS[1:]
    )
    row = type("Row", (), {"ticker": "INDF", "base_action": "WATCH", "cells": cells})()
    result = type("R", (), {"rows": (row,)})()

    text = _render_to_text(_setup_lens_impact_elements(result))
    assert "(no-entry)" in text
    # Full reason text is not printed in the compact table.
    assert "no standalone entry authority" not in text


def test_setup_lens_impact_warning_cell_renders_warning_not_action():
    from src.adapters.cli.today_commands import _setup_lens_impact_elements
    from src.application.use_case.evaluate_swing_setup_use_case import (
        AVAILABLE_SWING_SETUPS,
    )

    first = AVAILABLE_SWING_SETUPS[0]
    cells = (
        _cell(first, action=None, score=None, match="NO_MATCH", warning="no broker_detail"),
    ) + tuple(_cell(name) for name in AVAILABLE_SWING_SETUPS[1:])
    row = type("Row", (), {"ticker": "BBRI", "base_action": "WATCH", "cells": cells})()
    result = type("R", (), {"rows": (row,)})()

    text = _render_to_text(_setup_lens_impact_elements(result))
    # Rich table wrap can split the warning cell across lines/columns.
    assert "warning:" in text and "broker_detail" in text
    # Warning cell must not appear as a Next follow-up.
    assert f"saham plan swing BBRI --setup {first}" not in text


def test_today_no_candidates_shows_setup_lens_empty_message(tmp_path: Path):
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
    assert "SETUP LENS IMPACT" in result.stdout
    assert "No accumulation candidates to evaluate." in result.stdout


def test_today_never_renders_ticker_placeholder(tmp_path: Path):
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
    assert "TICKER" not in result.stdout


def test_setup_lens_next_commands_suppress_footer():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_setup_lens_impact_use_case import (
        DailySetupLensImpactCell,
        DailySetupLensImpactResult,
        DailySetupLensImpactRow,
    )
    from src.application.use_case.evaluate_swing_setup_use_case import (
        AVAILABLE_SWING_SETUPS,
    )

    cell = DailySetupLensImpactCell(
        setup_name=AVAILABLE_SWING_SETUPS[0],
        action="WATCH",
        signal_score=72,
        setup_match="MATCH",
        entry_authority=True,
        capped_reason=None,
        warning=None,
    )
    row = DailySetupLensImpactRow(
        ticker="BBCA",
        base_action="WATCH",
        cells=(cell,),
    )
    result = DailySetupLensImpactResult(rows=(row,))

    fake_response = type(
        "R",
        (),
        {
            "universe": "lq45",
            "universe_count": 45,
            "stale_count": 0,
            "regime": None,
            "opening_candidates": [],
            "market_wide_opening_observations": [],
            "accumulation_candidates": [],
            "accumulation_summary": None,
            "daily_accumulation_candidates": [],
            "warnings": [],
            "live_session_date": date(2026, 6, 19),
            "latest_completed_eod_date": date(2026, 6, 19),
            "opening_snapshot_date": None,
            "is_historical": True,
            "readiness_items": [],
            "overall_authority": "READY",
            "setup_lens_impact": result,
        },
    )()

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "saham plan swing BBCA --setup" in result.stdout
        assert "Next: saham screen accum" not in result.stdout
        assert "TICKER" not in result.stdout


def test_today_fallback_next_uses_first_accumulation_candidate():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_accumulation_projection import (
        DailyAccumulationCandidate,
    )
    from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=None,
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=0,
        readiness_items=[],
        overall_authority="READY",
        regime=None,
        opening_candidates=[],
        market_wide_opening_observations=[],
        accumulation_candidates=[],
        accumulation_summary=None,
        daily_accumulation_candidates=[
            DailyAccumulationCandidate(
                ticker="BBCA",
                accum_score=80.0,
                setup_phase="ACCUMULATION",
                signal_score=70,
                signal_authority_coverage=0.8,
                risk_status="OPEN",
                action="WATCH",
            )
        ],
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "Next: saham plan swing BBCA" in result.stdout


def test_today_fallback_next_fetches_when_not_ready():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=None,
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=41,
        readiness_items=[],
        overall_authority="NOT_READY",
        regime=None,
        opening_candidates=[],
        market_wide_opening_observations=[],
        accumulation_candidates=[],
        accumulation_summary=None,
        daily_accumulation_candidates=[],
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "Next: saham fetch market --universe lq45" in result.stdout


def test_today_fallback_next_screen_accum_when_no_candidates():
    from unittest.mock import MagicMock, patch

    from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse

    fake_response = DailyBriefingResponse(
        live_session_date=date(2026, 6, 19),
        latest_completed_eod_date=date(2026, 6, 19),
        opening_snapshot_date=None,
        is_historical=True,
        universe="lq45",
        universe_count=45,
        data_freshness=[],
        stale_count=0,
        readiness_items=[],
        overall_authority="READY",
        regime=None,
        opening_candidates=[],
        market_wide_opening_observations=[],
        accumulation_candidates=[],
        accumulation_summary=None,
        daily_accumulation_candidates=[],
        warnings=[],
    )

    with patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_uc.execute.return_value = fake_response

        result = runner.invoke(app, ["today", "--universe", "lq45", "--date", "2026-06-19"])
        assert result.exit_code == 0
        assert "Next: saham screen accum --universe lq45" in result.stdout


def test_daily_display():
    # Test C: Daily Display
    from rich.console import Console

    from src.adapters.cli.today_commands import _accumulation_screen_table
    from src.application.use_case.daily_accumulation_projection import DailyAccumulationCandidate

    candidate = DailyAccumulationCandidate(
        ticker="BBCA",
        accum_score=80.0,
        setup_phase="ACCUMULATION",
        signal_score=70,
        signal_authority_coverage=0.85,
        risk_status="OPEN",
        action="WATCH",
    )

    # Assert candidate constructor uses signal_authority_coverage
    assert candidate.signal_authority_coverage == 0.85
    # Assert no candidate field named coverage_score is used
    assert not hasattr(candidate, "coverage_score")

    console_inst = Console()
    with console_inst.capture() as capture:
        table = _accumulation_screen_table([candidate])
        console_inst.print(table)

    output = capture.get()
    # Assert output contains Authority
    assert "Authority" in output
    # Assert output contains expected percentage
    assert "85%" in output


# ── ADR-052: live-first resolution branching ──────────────────────────────────


def _fake_briefing_use_case(sentinel):
    """Use case whose execute() returns a sentinel cached response."""
    from unittest.mock import MagicMock

    uc = MagicMock()
    uc.execute.return_value = sentinel
    return uc


def _req(offline_universe="lq45", as_of=None):
    from src.application.use_case.daily_briefing_use_case import DailyBriefingRequest

    return DailyBriefingRequest(universe=offline_universe, top=3, as_of_date=as_of)


def test_resolve_offline_flag_skips_refresh():
    from unittest.mock import patch

    from src.adapters.cli import today_commands

    cached = object()
    uc = _fake_briefing_use_case(cached)
    with patch.object(today_commands, "_build_refresh_workspace_use_case") as build:
        res = today_commands._resolve_briefing_response(
            use_case=uc, request=_req(), offline=True, db_path=Path("x.db")
        )
    assert res.data_source == "CACHED"
    assert res.response is cached
    build.assert_not_called()
    uc.execute.assert_called_once()


def test_resolve_historical_skips_refresh():
    from unittest.mock import patch

    from src.adapters.cli import today_commands

    cached = object()
    uc = _fake_briefing_use_case(cached)
    with patch.object(today_commands, "_build_refresh_workspace_use_case") as build:
        res = today_commands._resolve_briefing_response(
            use_case=uc, request=_req(as_of=date(2026, 6, 19)), offline=False, db_path=Path("x.db")
        )
    assert res.data_source == "HISTORICAL"
    assert res.response is cached
    build.assert_not_called()


def test_resolve_lock_window_prefers_committed_corpus():
    from types import SimpleNamespace
    from unittest.mock import patch

    from src.adapters.cli import today_commands

    cached = object()
    uc = _fake_briefing_use_case(cached)
    pre_open = SimpleNamespace(is_pre_open=True)
    with (
        patch(
            "src.infrastructure.browser.stockbit_market_time.get_display_market_status",
            return_value=pre_open,
        ),
        patch.object(today_commands, "_build_refresh_workspace_use_case") as build,
    ):
        res = today_commands._resolve_briefing_response(
            use_case=uc, request=_req(), offline=False, db_path=Path("x.db")
        )
    assert res.data_source == "LOCK_WINDOW"
    assert res.response is cached
    build.assert_not_called()


def test_resolve_live_success_uses_refreshed_briefing():
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from src.adapters.cli import today_commands

    live_response = object()
    refresh_uc = MagicMock()
    refresh_uc.execute.return_value = SimpleNamespace(
        briefing=live_response, warnings=("1 ticker(s) failed during refresh.",)
    )
    uc = _fake_briefing_use_case(object())
    open_status = SimpleNamespace(is_pre_open=False)
    with (
        patch(
            "src.infrastructure.browser.stockbit_market_time.get_display_market_status",
            return_value=open_status,
        ),
        patch.object(today_commands, "_build_refresh_workspace_use_case", return_value=refresh_uc),
    ):
        res = today_commands._resolve_briefing_response(
            use_case=uc, request=_req(), offline=False, db_path=Path("x.db")
        )
    assert res.data_source == "LIVE"
    assert res.response is live_response
    assert res.extra_warnings == ["1 ticker(s) failed during refresh."]
    uc.execute.assert_not_called()  # live path did not fall back to cache


def test_resolve_live_failure_falls_back_to_cache_with_warning():
    from types import SimpleNamespace
    from unittest.mock import patch

    from src.adapters.cli import today_commands

    cached = object()
    uc = _fake_briefing_use_case(cached)
    open_status = SimpleNamespace(is_pre_open=False)

    def _boom(**_kwargs):
        raise ConnectionError("stockbit down")

    with (
        patch(
            "src.infrastructure.browser.stockbit_market_time.get_display_market_status",
            return_value=open_status,
        ),
        patch.object(today_commands, "_build_refresh_workspace_use_case", side_effect=_boom),
    ):
        res = today_commands._resolve_briefing_response(
            use_case=uc, request=_req(), offline=False, db_path=Path("x.db")
        )
    assert res.data_source == "CACHED"
    assert res.response is cached
    assert res.extra_warnings and "ConnectionError" in res.extra_warnings[0]
