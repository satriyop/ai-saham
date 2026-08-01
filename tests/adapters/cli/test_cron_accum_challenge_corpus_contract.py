"""Contract tests for the consolidated accum challenge-corpus cron wrapper (P1)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WRAPPER = (ROOT / "scripts" / "cron_accum_challenge_corpus.sh").read_text(encoding="utf-8")
INSTALL = (ROOT / "install_cron.sh").read_text(encoding="utf-8")
ACTIVE_CRON_LINES = tuple(line for line in INSTALL.splitlines() if line and line[0].isdigit())


def test_wrapper_uses_fail_closed_shell_and_ordered_chain() -> None:
    assert "set -euo pipefail" in WRAPPER
    capture_at = WRAPPER.index("research accum capture")
    sync_at = WRAPPER.index("research accum sync-session-calendar")
    labels_at = WRAPPER.index("research accum labels")
    status_at = WRAPPER.index("research accum status")
    assert capture_at < sync_at < labels_at < status_at
    assert "--universe lq45" in WRAPPER
    assert "--all-label-contracts" in WRAPPER
    assert "--auto" in WRAPPER
    # Completion marker only after the full chain (appears last).
    assert WRAPPER.rindex("COMPLETION_OK") > status_at


def test_wrapper_does_not_emit_completion_before_status() -> None:
    # Source order: no COMPLETION_OK string before status command.
    before_status, after_status = WRAPPER.split("research accum status", 1)
    assert "COMPLETION_OK" not in before_status
    assert "COMPLETION_OK" in after_status


def test_wrapper_syncs_calendar_before_labels() -> None:
    sync_at = WRAPPER.index("sync-session-calendar")
    labels_at = WRAPPER.index("research accum labels")
    assert sync_at < labels_at


def test_wrapper_documents_recovery_and_collecting_as_success() -> None:
    assert "idempotent" in WRAPPER.lower() or "Re-run this script" in WRAPPER
    assert "COLLECTING" in WRAPPER
    assert "Do not attach snapshots to legacy" in WRAPPER


def test_install_cron_uses_single_wrapper_entry_not_split_jobs() -> None:
    wrapper_lines = [line for line in ACTIVE_CRON_LINES if "cron_accum_challenge_corpus.sh" in line]
    assert len(wrapper_lines) == 1
    assert wrapper_lines[0].startswith("15 19 * * 1-5 ")
    # Split capture/labels cron lines must be gone (single operator surface).
    for line in ACTIVE_CRON_LINES:
        assert not ("research accum capture" in line and "cron_accum_challenge_corpus" not in line)
        assert not ("research accum labels" in line and "cron_accum_challenge_corpus" not in line)


def test_legacy_split_cron_test_expectations_updated() -> None:
    """install_cron must not schedule bare capture/labels as separate active lines."""
    for line in ACTIVE_CRON_LINES:
        if "research accum" in line:
            assert "cron_accum_challenge_corpus.sh" in line
