"""JSON output shape and save-behavior tests."""

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.adapters.cli import screen_accum_commands as accum_cli
from src.adapters.cli.main import app
from src.application.dto.accumulation_screen import AccumulationScreenResponse
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowUseCase,
)
from tests.adapters.cli.screen_accum_test_fixtures import (
    _candidate,
    _fake_workflow_result,
    runner,
)


def _real_workflow_uc(screen_execute, broker_repo=None):
    """Wire the real workflow use case (not a fake) so vwap_only/squeeze_only/
    top/sort_by filtering actually runs through the S2 projector, letting
    these tests verify JSON/table parity end-to-end."""
    screen_mock = MagicMock()
    screen_mock.execute.side_effect = screen_execute
    swing_config = SimpleNamespace(
        tier1_broker_codes=frozenset({"AK", "BK"}),
        bci_cluster_min_count=3,
        bci_stable_min_count=1,
        min_market_cap_idr=0,
        resistance_gate_enabled=True,
        resistance_headroom_min_pct=5.0,
        ex_date_warning_days=10,
        sector_breadth_enabled=True,
        sector_breadth_threshold=0.60,
        sector_breadth_bonus_pts=10.0,
        sector_breadth_min_tickers=3,
        smart_money_brokers=("BK", "AK"),
        noise_brokers=("YP", "XC"),
    )
    accum_config = SimpleNamespace(
        min_foreign_flow_score=SimpleNamespace(enabled=False, value=0.0),
        min_signal_score=SimpleNamespace(enabled=False, value=0.0),
        foreign_flow_score_policy=None,
        derived_features=None,
        display=SimpleNamespace(
            coiled_spring_min_foreign_flow_score=50.0,
            coiled_spring_bb_pctile=0.20,
        ),
    )
    if broker_repo is None:
        broker_repo = MagicMock()
        broker_repo.get_broker_daily_flows.return_value = []
    return RunAccumulationScreenWorkflowUseCase(
        screen_use_case=screen_mock,
        broker_repository=broker_repo,
        market_repository=MagicMock(),
        swing_config=swing_config,
        accumulation_screener_config=accum_config,
        rules_loader=MagicMock(),
        indicator_registry_factory=MagicMock(),
        save_watchlist_use_case=None,
    )


def test_screen_accum_json_includes_setup_phase(monkeypatch):
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState

    setup_phase = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.COMPRESSION,
        previous_phase=SetupPhaseState.ACCUMULATION,
        phase_age_sessions=2,
        phase_strength=0.7,
        coverage_score=0.8,
        conviction_score=0.56,
        sequence_valid=True,
    )

    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            response=AccumulationScreenResponse(
                candidates=[_candidate(setup_phase=setup_phase)],
                screened_at=date(2026, 6, 28),
                window_days=getattr(req, "window", 7),
                total_tickers_checked=len(req.tickers),
                tickers_skipped=0,
                provider="fake",
            )
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(app, ["screen", "accum", "INDF", "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    candidate_json = payload["candidates"][0]
    assert "setup_phase" in candidate_json
    assert candidate_json["setup_phase"]["current_phase"] == "COMPRESSION"
    assert candidate_json["setup_phase"]["previous_phase"] == "ACCUMULATION"


def test_screen_accum_json_includes_typed_freshness(monkeypatch):
    """S3: JSON must carry typed freshness fields, no bare "OK" state, and
    it must come from the same DataFreshnessStatus the table renders."""

    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            response=AccumulationScreenResponse(
                candidates=[
                    _candidate(
                        latest_candle_date=date(2026, 6, 26),
                        latest_broker_date=date(2026, 6, 26),
                    )
                ],
                screened_at=date(2026, 6, 28),
                window_days=getattr(req, "window", 7),
                total_tickers_checked=len(req.tickers),
                tickers_skipped=0,
                provider="fake",
            )
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(app, ["screen", "accum", "INDF", "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    freshness = payload["candidates"][0]["freshness"]

    assert freshness["candle_as_of"] == "2026-06-26"
    assert freshness["broker_as_of"] == "2026-06-26"
    assert freshness["alignment_state"] == "ALIGNED"
    assert freshness["sources_aligned"] is True
    assert isinstance(freshness["candle_state"], str)
    assert isinstance(freshness["broker_state"], str)
    assert freshness["candle_state"] != "OK"
    assert freshness["broker_state"] != "OK"
    assert freshness["alignment_state"] != "OK"
    assert "OK" not in result.output


def test_screen_accum_save_calls_use_case(monkeypatch):
    from src.application.use_case.save_screen_watchlist_use_case import (
        SaveScreenWatchlistResult,
    )

    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            response=AccumulationScreenResponse(
                candidates=[_candidate(
                    ticker="BBCA", foreign_flow_score=80.0, bci_label="CLUSTER",
                )],
                screened_at=date(2026, 6, 28),
                window_days=getattr(req, "window", 7),
                total_tickers_checked=len(req.tickers),
                tickers_skipped=0,
                provider="fake",
            ),
            save_result=SaveScreenWatchlistResult(
                saved_count=1, name="mywatch"
            ),
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--save", "mywatch"],
    )

    assert result.exit_code == 0, (
        f"exit {result.exit_code} stdout={result.output!r} exc={result.exception}"
    )
    assert "✓ Saved" in result.output
    assert "mywatch" in result.output


def test_screen_accum_json_save_fails_explicitly(monkeypatch):
    """S2: --save with --format json is an unsupported combo — must fail
    clearly, not silently drop the save (not just warn-and-skip either)."""

    def fake_uc(**kwargs):
        raise AssertionError("workflow use case must not run for a rejected combo")

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--format", "json", "--save", "mywatch"],
    )

    assert result.exit_code != 0
    assert "--save" in result.output
    assert "--format json" in result.output


def test_screen_accum_multi_save_fails_explicitly(monkeypatch):
    """S2: --save with --multi is an unsupported combo — must fail clearly,
    not silently drop the save (not just warn-and-skip either)."""

    def fake_uc(**kwargs):
        raise AssertionError("workflow use case must not run for a rejected combo")

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--multi", "--save", "mywatch"],
    )

    assert result.exit_code != 0
    assert "--save" in result.output
    assert "--multi" in result.output


def test_screen_accum_single_json_matches_table_candidates_under_vwap_only(monkeypatch):
    """S2: --vwap-only --format json must return the same candidate set the
    table would show — not response.candidates[:top] unfiltered."""
    underwater = _candidate(ticker="A", vwap_discount_pct=5.0)
    not_underwater = _candidate(ticker="B", vwap_discount_pct=-2.0)

    def screen_execute(req):
        return AccumulationScreenResponse(
            candidates=[underwater, not_underwater],
            screened_at=date(2026, 7, 14),
            window_days=req.window_days,
            total_tickers_checked=2,
            tickers_skipped=0,
            provider="fake",
        )

    workflow_uc = _real_workflow_uc(screen_execute)
    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        lambda **kwargs: workflow_uc,
    )

    captured_table_candidates = {}
    from src.adapters.cli import screen_accum_single_display as single_display_mod

    original_display_results = single_display_mod.display_results

    def spy_display_results(*, candidates, **kwargs):
        captured_table_candidates["tickers"] = [c.ticker for c in candidates]
        return original_display_results(candidates=candidates, **kwargs)

    monkeypatch.setattr(accum_cli, "display_results", spy_display_results)

    table_result = runner.invoke(app, ["screen", "accum", "A", "B", "--vwap-only"])
    assert table_result.exit_code == 0, table_result.output

    json_result = runner.invoke(
        app, ["screen", "accum", "A", "B", "--vwap-only", "--format", "json"]
    )
    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(json_result.output)
    json_tickers = [c["ticker"] for c in payload["candidates"]]

    assert json_tickers == ["A"]
    assert captured_table_candidates["tickers"] == ["A"]
    assert json_tickers == captured_table_candidates["tickers"]
    assert payload["applied_filters"]["vwap_only"] is True
    assert payload["counts_before_filter"] == 2
    assert payload["counts_after_filter"] == 1


def test_screen_accum_multi_json_matches_table_rows_under_top_sort_squeeze(monkeypatch):
    """S2: --multi --top --sort-by --squeeze-only must produce the same row
    set in JSON as in the table — not every candidate from every window."""
    tight_hot = _candidate(ticker="A", foreign_flow_score=90.0, bb_width_pctile=0.10)
    loose_hot = _candidate(ticker="B", foreign_flow_score=95.0, bb_width_pctile=0.80)
    tight_cold = _candidate(ticker="C", foreign_flow_score=20.0, bb_width_pctile=0.10)

    def screen_execute(req):
        return AccumulationScreenResponse(
            candidates=[tight_hot, loose_hot, tight_cold],
            screened_at=date(2026, 7, 14),
            window_days=req.window_days,
            total_tickers_checked=3,
            tickers_skipped=0,
            provider="fake",
        )

    workflow_uc = _real_workflow_uc(screen_execute)
    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        lambda **kwargs: workflow_uc,
    )

    captured_table_rows = {}
    from src.adapters.cli import screen_accum_multi_display as multi_display_mod

    original_display_multi = multi_display_mod.display_multi

    def spy_display_multi(*, rows, **kwargs):
        captured_table_rows["tickers"] = [r.ticker for r in rows]
        return original_display_multi(rows=rows, **kwargs)

    monkeypatch.setattr(accum_cli, "display_multi", spy_display_multi)

    table_result = runner.invoke(
        app,
        ["screen", "accum", "A", "B", "C", "--multi", "--squeeze-only", "--top", "1"],
    )
    assert table_result.exit_code == 0, table_result.output

    json_result = runner.invoke(
        app,
        [
            "screen", "accum", "A", "B", "C", "--multi", "--squeeze-only",
            "--top", "1", "--format", "json",
        ],
    )
    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(json_result.output)
    json_tickers = list(payload["tickers"].keys())

    assert json_tickers == ["A"]
    assert captured_table_rows["tickers"] == ["A"]
    assert json_tickers == captured_table_rows["tickers"]
    assert payload["applied_filters"]["squeeze_only"] is True
    assert payload["applied_filters"]["top"] == 1
    assert payload["counts_before_filter"] == 3
    assert payload["counts_after_filter"] == 1


def test_screen_accum_multi_renders_tracked_broker_flow_not_broker_quality(monkeypatch):
    """Tracked Broker Flow rename: table header says 'Tracked Broker Flow',
    JSON key is 'tracked_broker_flow' (never 'broker_quality'), and scope is
    explicit as 'tracked_brokers' — never implying full-market composition."""
    from src.domain.entities.broker_flow import BrokerDailyFlow

    candidate = _candidate(ticker="A")

    def screen_execute(req):
        return AccumulationScreenResponse(
            candidates=[candidate],
            screened_at=date(2026, 7, 14),
            window_days=req.window_days,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="fake",
        )

    broker_repo = MagicMock()
    broker_repo.get_broker_daily_flows.return_value = [
        BrokerDailyFlow(
            ticker="A",
            broker_code="AK",
            broker_name="AK",
            date=date(2026, 7, 14),
            buy_lot=100,
            sell_lot=0,
            net_lot=100,
            buy_value=Decimal("10000000"),
            sell_value=Decimal("0"),
            net_value=Decimal("10000000"),
            avg_buy_price=Decimal("1000"),
            avg_sell_price=Decimal("1000"),
            avg_price=Decimal("1000"),
            buy_pct=1.0,
            sell_pct=0.0,
        )
    ]

    workflow_uc = _real_workflow_uc(screen_execute, broker_repo=broker_repo)
    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        lambda **kwargs: workflow_uc,
    )

    table_result = runner.invoke(app, ["screen", "accum", "A", "--multi"])
    assert table_result.exit_code == 0, table_result.output
    assert "Tracked Broker Flow" in table_result.output
    assert "Broker Flow" not in table_result.output.replace("Tracked Broker Flow", "")

    json_result = runner.invoke(
        app, ["screen", "accum", "A", "--multi", "--format", "json"]
    )
    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(json_result.output)
    entry = payload["tickers"]["A"]

    assert "tracked_broker_flow" in entry
    assert "broker_quality" not in entry
    assert entry["tracked_broker_flow"]["scope"] == "tracked_brokers"
    assert entry["tracked_broker_flow"]["label"] == "smart+"


def test_screen_accum_multi_json_includes_typed_freshness_per_window(monkeypatch):
    """S3 follow-up: multi-window JSON must carry per-window typed freshness,
    not null, for every projected {window}_sessions candidate."""
    candidate = _candidate(
        ticker="A",
        latest_candle_date=date(2026, 7, 13),
        latest_broker_date=date(2026, 7, 13),
    )

    def screen_execute(req):
        return AccumulationScreenResponse(
            candidates=[candidate],
            screened_at=date(2026, 7, 14),
            window_days=req.window_days,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="fake",
        )

    workflow_uc = _real_workflow_uc(screen_execute)
    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        lambda **kwargs: workflow_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "A", "--multi", "--windows", "7,30", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    entry = payload["tickers"]["A"]

    checked_any = False
    for key in ("7_sessions", "30_sessions"):
        window_candidate = entry[key]
        if window_candidate is None:
            continue
        checked_any = True
        freshness = window_candidate["freshness"]
        assert freshness is not None
        assert freshness["candle_as_of"] == "2026-07-13"
        assert freshness["broker_as_of"] == "2026-07-13"
        assert isinstance(freshness["alignment_state"], str)
        assert freshness["alignment_state"] == "ALIGNED"
        assert freshness["alignment_state"] != "OK"
    assert checked_any


def test_screen_accum_multi_duplicate_windows_fails_clearly(monkeypatch):
    def screen_execute(req):
        return AccumulationScreenResponse(
            candidates=[],
            screened_at=date(2026, 7, 14),
            window_days=req.window_days,
            total_tickers_checked=0,
            tickers_skipped=0,
            provider="fake",
        )

    workflow_uc = _real_workflow_uc(screen_execute)
    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        lambda **kwargs: workflow_uc,
    )

    result = runner.invoke(
        app, ["screen", "accum", "BBCA", "--multi", "--windows", "7,7,30"]
    )

    assert result.exit_code != 0
    assert "Duplicate windows" in result.output


def test_screen_accum_invalid_sort_by_fails_clearly(monkeypatch):
    def screen_execute(req):
        return AccumulationScreenResponse(
            candidates=[],
            screened_at=date(2026, 7, 14),
            window_days=req.window_days,
            total_tickers_checked=0,
            tickers_skipped=0,
            provider="fake",
        )

    workflow_uc = _real_workflow_uc(screen_execute)
    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        lambda **kwargs: workflow_uc,
    )

    result = runner.invoke(
        app, ["screen", "accum", "BBCA", "--multi", "--sort-by", "banana"]
    )

    assert result.exit_code != 0
    assert "Invalid --sort-by" in result.output


def test_screen_accum_single_json_includes_universe_warnings_partial_result(monkeypatch):
    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            response=AccumulationScreenResponse(
                candidates=[_candidate(ticker="BBCA")],
                screened_at=date(2026, 6, 28),
                window_days=7,
                total_tickers_checked=1,
                tickers_skipped=1,
                provider="fake",
            ),
            warnings=("some warning",),
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app, ["screen", "accum", "BBCA", "--universe", "lq45", "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output[result.output.index("{"):])
    assert payload["universe"] == "lq45"
    assert payload["warnings"] == ["some warning"]
    assert payload["partial_result"] is True


def test_screen_accum_single_json_partial_result_false_when_nothing_skipped(monkeypatch):
    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            response=AccumulationScreenResponse(
                candidates=[_candidate(ticker="BBCA")],
                screened_at=date(2026, 6, 28),
                window_days=7,
                total_tickers_checked=1,
                tickers_skipped=0,
                provider="fake",
            ),
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(app, ["screen", "accum", "BBCA", "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["warnings"] == []
    assert payload["partial_result"] is False


def test_screen_accum_multi_json_includes_universe_warnings_partial_result(monkeypatch):
    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            multi_results={
                7: AccumulationScreenResponse(
                    candidates=[_candidate()],
                    screened_at=date(2026, 6, 28),
                    window_days=7,
                    total_tickers_checked=1,
                    tickers_skipped=1,
                    provider="fake",
                ),
            },
            warnings=("multi warning",),
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--multi", "--universe", "lq45", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output[result.output.index("{"):])
    assert payload["universe"] == "lq45"
    assert payload["warnings"] == ["multi warning"]
    assert payload["partial_result"] is True


def test_screen_accum_multi_json_partial_result_false_when_nothing_skipped(monkeypatch):
    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            multi_results={
                7: AccumulationScreenResponse(
                    candidates=[_candidate()],
                    screened_at=date(2026, 6, 28),
                    window_days=7,
                    total_tickers_checked=1,
                    tickers_skipped=0,
                    provider="fake",
                ),
            },
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app, ["screen", "accum", "BBCA", "--multi", "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["warnings"] == []
    assert payload["partial_result"] is False
