"""Contract tests for the shared accumulation observation corpus producer (P1)."""

from __future__ import annotations

import inspect
from pathlib import Path

from src.adapters.cli import research_accum_backfill_commands as backfill_mod
from src.adapters.cli import research_accum_capture_commands as capture_mod


def test_capture_and_backfill_share_run_signal_observation_corpus_write() -> None:
    """Both CLIs must call the single shared producer, not a fork."""
    assert capture_mod.run_signal_observation_corpus_write is (
        backfill_mod.run_signal_observation_corpus_write
    )
    capture_src = inspect.getsource(capture_mod.signal_capture_observations)
    assert "run_signal_observation_corpus_write" in capture_src
    assert "classify_accum_session_capture" in inspect.getsource(capture_mod)
    # Capture is single-session: start_date == end_date == session.
    assert "start_date=session_date" in capture_src
    assert "end_date=session_date" in capture_src


def test_catch_up_uses_shared_producer_for_missing_sessions_only() -> None:
    catch_up_src = inspect.getsource(capture_mod.signal_catch_up_observations)
    assert "missing_ihsg_sessions" in catch_up_src
    assert "run_signal_observation_corpus_write" in catch_up_src
    assert "start_date=session_date" in catch_up_src
    assert "end_date=session_date" in catch_up_src


def test_shared_producer_ensures_snapshots_before_observation_backfill() -> None:
    """Atomic snapshot ensure must precede BackfillSignalObservationsUseCase.execute."""
    source = inspect.getsource(backfill_mod.run_signal_observation_corpus_write)
    # Docstring mentions the backfill use case name; measure live call sites only.
    ensure_call = source.index("EnsureAccumulationPolicySnapshotsUseCase(learning_repo).execute")
    backfill_construct = source.index("return BackfillSignalObservationsUseCase(")
    assert ensure_call < backfill_construct
    assert 'universe_membership_source=f"{universe}@pit"' in source
    assert "disable_score_filters=True" in source
    # Production hard-filter object (pre-neutralization) is what ensure receives.
    assert "hard_filter_policy=production_policy_bundle.hard_filter_policy" in source


def test_shared_producer_module_documents_lq45_operational_universe() -> None:
    """Operational cron uses lq45; code path accepts universe string (PIT stamped)."""
    # Structural: capture option default help mentions lq45; install cron asserts separately.
    capture_src = Path(capture_mod.__file__).read_text(encoding="utf-8")
    assert "lq45" in capture_src
    # No second corpus-write function in the capture module.
    assert capture_src.count("def run_signal_observation_corpus_write") == 0
