"""Operational contract tests for the database-owned cron installer."""

from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[3] / "install_cron.sh").read_text()
ACTIVE_CRON_LINES = tuple(line for line in SCRIPT.splitlines() if line and line[0].isdigit())


def test_pre_open_schedule_stays_inside_authoritative_window() -> None:
    assert any(
        line.startswith("56 8 * * 1-5 ") and "saham fetch iev" in line for line in ACTIVE_CRON_LINES
    )
    assert any(
        line.startswith("57 8 * * 1-5 ") and "saham research pre-open capture" in line
        for line in ACTIVE_CRON_LINES
    )
    assert not any(line.startswith("58 8 * * 1-5 ") for line in ACTIVE_CRON_LINES)


def test_cron_uses_database_owned_pre_open_lifecycle_only() -> None:
    assert "saham research pre-open track --broker-confirm" in SCRIPT
    assert "saham research pre-open labels --format json" in SCRIPT
    assert "saham research pre-open evaluate --format json" in SCRIPT

    forbidden = (
        "saham research pre-open grade",
        "saham research pre-open prompt",
        "saham research pre-open tune",
        "--track-file",
        "data/opening/",
        "saham research signal",
        "AI tuning",
        "saham trade confirm",
        "trade log intraday",
    )
    for removed_route in forbidden:
        assert removed_route not in SCRIPT


def test_cron_activates_accumulation_capture_and_labels() -> None:
    assert any(
        line.startswith("15 19 * * 1-5 ")
        and "saham research accum capture" in line
        and "--universe lq45" in line
        for line in ACTIVE_CRON_LINES
    )
    assert any(
        line.startswith("45 19 * * 1-5 ")
        and "saham research accum labels" in line
        and "--all-label-contracts" in line
        for line in ACTIVE_CRON_LINES
    )
    # Active lines must not be commented; old route name must be gone
    for line in ACTIVE_CRON_LINES:
        if "research accum" in line:
            assert not line.lstrip().startswith("#")
            assert "research accumulation" not in line
            assert "tactical_3d" not in line
            assert "swing_10d" not in line


def test_cron_does_not_require_dotenv_to_activate_project() -> None:
    assert "[ -f .env ] && set -a" not in SCRIPT
    assert "if [ -f .env ]; then set -a; source .env; set +a; fi;" in SCRIPT
