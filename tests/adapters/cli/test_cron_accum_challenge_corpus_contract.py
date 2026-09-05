"""Contract tests for the consolidated accum challenge-corpus cron wrapper (P1)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WRAPPER_PATH = ROOT / "scripts" / "cron_accum_challenge_corpus.sh"
WRAPPER = WRAPPER_PATH.read_text(encoding="utf-8")
INSTALL = (ROOT / "install_cron.sh").read_text(encoding="utf-8")
ACTIVE_CRON_LINES = tuple(line for line in INSTALL.splitlines() if line and line[0].isdigit())


def test_wrapper_uses_fail_closed_shell_and_ordered_chain() -> None:
    assert "set -euo pipefail" in WRAPPER
    fetch_at = WRAPPER.index("saham fetch market --universe lq45 --candles-only")
    catch_up_at = WRAPPER.index("saham research accum catch-up")
    capture_at = WRAPPER.index("saham research accum capture")
    sync_at = WRAPPER.index("saham research accum sync-session-calendar")
    labels_at = WRAPPER.index("saham research accum labels")
    status_at = WRAPPER.index("saham research accum status")
    assert fetch_at < catch_up_at < capture_at < sync_at < labels_at < status_at
    assert "continuing today's capture" in WRAPPER
    assert "--universe lq45" in WRAPPER
    assert "--all-label-contracts" in WRAPPER
    assert "--auto" in WRAPPER
    assert "--require-session" in WRAPPER
    assert "--require-operational-success" in WRAPPER
    assert "--lookback-days 14" in WRAPPER
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


def test_install_cron_uses_wrapper_entries_not_split_jobs() -> None:
    wrapper_lines = [line for line in ACTIVE_CRON_LINES if "cron_accum_challenge_corpus.sh" in line]
    assert len(wrapper_lines) == 2
    assert wrapper_lines[0].startswith("15 19 * * 1-5 ")
    assert wrapper_lines[1].startswith("45 20 * * 1-5 ")
    # Split capture/labels cron lines must be gone (wrapper is the operator surface).
    for line in ACTIVE_CRON_LINES:
        assert not ("research accum capture" in line and "cron_accum_challenge_corpus" not in line)
        assert not ("research accum labels" in line and "cron_accum_challenge_corpus" not in line)


def _run_wrapper(
    tmp_path: Path,
    *,
    status: str,
    status_exit: int,
    fail_subcommand: str | None = None,
) -> subprocess.CompletedProcess:
    isolated_root = tmp_path / "isolated-repo"
    scripts_dir = isolated_root / "scripts"
    bin_dir = isolated_root / ".venv" / "bin"
    scripts_dir.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    wrapper_copy = scripts_dir / WRAPPER_PATH.name
    wrapper_copy.write_text(WRAPPER, encoding="utf-8")
    command_log = isolated_root / "saham-commands.log"
    fake_saham = bin_dir / "saham"
    fake_saham.write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_SAHAM_LOG"
case "$*" in
  *"research accum catch-up"*)
    if [ "$FAIL_SUBCOMMAND" = "catch-up" ]; then
      printf '{"error":"empty_on_trading_session"}\\n' >&2
      exit 3
    fi
    ;;
  *"research accum status"*)
    case "$*" in
      *"--require-operational-success"*) ;;
      *) exit 88 ;;
    esac
    printf '{"cohorts":[{"producer_status":"%s"}]}\\n' "$FAKE_STATUS"
    exit "$FAKE_STATUS_EXIT"
    ;;
esac
printf '{}\\n'
""",
        encoding="utf-8",
    )
    fake_saham.chmod(0o755)
    (bin_dir / "activate").write_text(
        f'PATH="{bin_dir}:$PATH"\nexport PATH\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "ACCUM_CORPUS_SESSION": "2026-08-07",
            "FAKE_STATUS": status,
            "FAKE_STATUS_EXIT": str(status_exit),
            "FAKE_SAHAM_LOG": str(command_log),
            "FAIL_SUBCOMMAND": fail_subcommand or "",
        }
    )
    return subprocess.run(
        ["/bin/bash", str(wrapper_copy)],
        cwd=isolated_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_wrapper_execution_stops_before_completion_when_operational_gate_fails(
    tmp_path: Path,
) -> None:
    result = _run_wrapper(tmp_path, status="BLOCKED_POLICY", status_exit=1)

    assert result.returncode == 1
    assert '"producer_status":"BLOCKED_POLICY"' in result.stdout
    assert "COMPLETION_OK" not in result.stdout
    assert "status ok" not in result.stderr


@pytest.mark.parametrize("status", ["COLLECTING", "CHALLENGE_INPUT_READY"])
def test_wrapper_execution_emits_completion_after_operational_gate_passes(
    tmp_path: Path,
    status: str,
) -> None:
    result = _run_wrapper(tmp_path, status=status, status_exit=0)

    assert result.returncode == 0
    assert f'"producer_status":"{status}"' in result.stdout
    assert "COMPLETION_OK session=2026-08-07" in result.stdout
    assert "status ok" in result.stderr


def test_wrapper_continues_today_chain_when_catch_up_fails(tmp_path: Path) -> None:
    result = _run_wrapper(
        tmp_path,
        status="COLLECTING",
        status_exit=0,
        fail_subcommand="catch-up",
    )
    commands = (tmp_path / "isolated-repo" / "saham-commands.log").read_text(encoding="utf-8")

    assert result.returncode == 3
    assert "COMPLETION_OK" not in result.stdout
    assert "continuing today's capture" in result.stderr
    assert "skipping COMPLETION_OK" in result.stderr
    assert "research accum capture" in commands
    assert "sync-session-calendar" in commands
    assert "research accum labels" in commands
    assert "research accum status" in commands


def test_legacy_split_cron_test_expectations_updated() -> None:
    """install_cron must not schedule bare capture/labels as separate active lines."""
    for line in ACTIVE_CRON_LINES:
        if "research accum" in line:
            assert "cron_accum_challenge_corpus.sh" in line
