from unittest.mock import MagicMock, patch

from src.adapters.cli.screen_accum_commands import accumulation_run
from src.adapters.cli.screen_accum_formatters import (
    AccumulationDisplayConfig,
    classify_pattern,
    fmt_score,
)


def test_screen_accum_commands_uses_shared_deps_and_passes_display_config():
    """Clean break: config and workflow come from build_screen_deps."""
    pkg = "src.adapters.cli.screen_accum_commands"
    deps = MagicMock()
    deps.swing_policy = MagicMock()
    deps.screener_config = MagicMock()
    deps.broker_repository = MagicMock()
    mock_wf = MagicMock()
    mock_wf.execute.return_value = MagicMock(
        warnings=[],
        response=MagicMock(
            candidates=[],
            screened_at="2026-06-19",
            window_days=7,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="fake",
        ),
        single_projection=MagicMock(candidates=[], to_dict=lambda: {}),
        save_result=None,
        effective_session=None,
    )
    deps.build_accum_workflow_use_case.return_value = mock_wf
    display_config = AccumulationDisplayConfig(
        enter_min_accum_score=70.0,
        watch_min_accum_score=55.0,
        coiled_spring_min_accum_score=50.0,
        coiled_spring_bb_pctile=0.20,
        accum_score_policy=None,
    )

    with (
        patch(f"{pkg}.build_screen_deps", return_value=deps) as mock_deps,
        patch(f"{pkg}.resolve_tickers", return_value=["BBCA"]),
        patch(
            f"{pkg}.accumulation_display_config_from_screener",
            return_value=display_config,
        ),
        patch(f"{pkg}.display_results") as mock_display_results,
    ):
        accumulation_run(tickers=["BBCA"])

        mock_deps.assert_called_once()
        deps.build_accum_workflow_use_case.assert_called_once()
        mock_display_results.assert_called_once()
        assert mock_display_results.call_args[1]["display_config"] is display_config


def test_fmt_score_uses_explicit_thresholds():
    display_config = AccumulationDisplayConfig(
        enter_min_accum_score=70.0,
        watch_min_accum_score=55.0,
        coiled_spring_min_accum_score=50.0,
        coiled_spring_bb_pctile=0.20,
        accum_score_policy=None,
    )
    # smoke: formatter accepts display_config
    out = fmt_score(70.0, display_config=display_config)
    assert out is not None
    _ = classify_pattern
