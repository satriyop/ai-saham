from unittest.mock import MagicMock, patch

from src.adapters.cli.screen_accum_commands import accumulation_run
from src.adapters.cli.screen_accum_formatters import (
    AccumulationDisplayConfig,
    classify_pattern,
    fmt_score,
)


def test_screen_accum_commands_loads_config_once_and_passes_display_config():
    pkg = "src.adapters.cli.screen_accum_commands"
    with patch(f"{pkg}._load_swing_config") as mock_load_sc, \
         patch(f"{pkg}._load_accumulation_screener_config") as mock_load_asc, \
         patch(f"{pkg}.create_run_accumulation_screen_workflow_use_case") as mock_create_wf, \
         patch(f"{pkg}.resolve_tickers", return_value=["BBCA"]), \
         patch(f"{pkg}.display_results") as mock_display_results:

        mock_wf = MagicMock()
        mock_wf.execute.return_value = MagicMock(
            warnings=[],
            response=MagicMock(candidates=[], screened_at="2026-06-19"),
            save_result=None
        )
        mock_create_wf.return_value = mock_wf

        # Run accumulation
        accumulation_run(tickers=["BBCA"])

        mock_load_sc.assert_called_once()
        mock_load_asc.assert_called_once()
        # Verify display_results was called with the display_config
        mock_display_results.assert_called_once()
        call_kwargs = mock_display_results.call_args[1]
        assert "display_config" in call_kwargs


def test_fmt_score_uses_explicit_thresholds():
    display_config = AccumulationDisplayConfig(
        enter_min_accum_score=70.0,
        watch_min_accum_score=50.0,
        coiled_spring_min_accum_score=60.0,
        coiled_spring_bb_pctile=0.2,
        accum_score_policy=None
    )

    # 71 is >= enter_min (70) -> should be green (contains ansi sequence / style for green)
    score_71 = fmt_score(71.0, display_config)
    assert "32m" in score_71 or "green" in score_71

    # 55 is >= watch_min (50) and < enter_min -> should be yellow
    score_55 = fmt_score(55.0, display_config)
    assert "33m" in score_55 or "yellow" in score_55

    # 40 is < watch_min -> should be white
    score_40 = fmt_score(40.0, display_config)
    assert "37m" in score_40 or "white" in score_40


def test_classify_pattern_uses_explicit_thresholds():
    display_config = AccumulationDisplayConfig(
        enter_min_accum_score=70.0,
        watch_min_accum_score=50.0,
        coiled_spring_min_accum_score=60.0,
        coiled_spring_bb_pctile=0.15,
        accum_score_policy=None
    )

    from src.application.dto.accumulation_screen import AccumulationCandidate

    # Create candidates
    c_strong = MagicMock(spec=AccumulationCandidate)
    c_strong.accum_score = 65.0  # above coiled_spring_min_accum_score (60.0)
    c_strong.bb_width_pctile = 0.10     # below coiled_spring_bb_pctile (0.15)

    # Should classify as coiled spring
    pattern = classify_pattern(
        windows=[7],
        candidates_by_window={7: c_strong},
        display_config=display_config
    )
    assert pattern == "coiled spring"
