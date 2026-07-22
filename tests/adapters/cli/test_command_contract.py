"""Contract tests for the public CLI command tree."""

import re
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli import (
    fetch_commands,
    fetch_iev_commands,
    screen_lifecycle_commands,
    screen_pre_open_commands,
    trade_commands,
    trade_intraday_commands,
)
from src.adapters.cli.main import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[3]


EXPECTED_COMMANDS: dict[tuple[str, ...], tuple[str, ...]] = {
    (): (
        "today",
        "tui",
        "fetch",
        "audit",
        "screen",
        "learn",
        "research",
        "view",
        "indicator",
        "analyze",
        "strategy",
        "trade",
    ),
    ("audit",): ("data",),
    ("audit", "data"): (
        "manifest",
        "source-contracts",
        "reconcile-sources",
        "contract-gate",
        "seasonality-cleanup-plan",
        "repair-seasonality-cache",
        "candidate-observation-identity",
        "repair-candidate-observations",
        "repair-signal-forward-labels",
    ),
    ("fetch",): (
        "market",
        "broker",
        "broker-import",
        "broker-history",
        "broker-top-foreign",
        "iev",
        "status",
        "stockbit",
        "universe",
        "audit",
        "enrichment-history",
        "calendar",
    ),
    ("fetch", "stockbit"): ("login", "status", "spy", "test", "browse", "fetch-top5"),
    ("fetch", "universe"): ("list", "update", "inspect", "create"),
    ("screen",): ("pre-open", "accum", "watchlist", "compare"),
    ("learn",): ("snapshot", "track", "grade", "prompt", "tune"),
    ("research",): ("signal", "accumulation"),
    ("research", "signal"): ("backfill", "capture", "labels", "replay", "readiness"),
    ("research", "accumulation"): ("evaluate",),
    ("indicator",): ("compute", "snapshot", "create", "list", "show", "delete"),
    ("analyze",): (
        "risk",
        "compare",
        "sentiment",
        "audit",
        "regime",
        "swing",
        "swing-compare",
        "chart",
        "signal",
    ),
    ("analyze", "signal"): ("inspect",),
    ("analyze", "chart"): ("price", "rsi", "volume"),
    ("view",): ("broker", "universe", "market-context"),
    ("view", "broker"): (
        "status",
        "flow",
        "top",
        "history",
        "top-foreign",
        "distribution",
        "mappings",
    ),
    ("view", "market-context"): (),
    ("trade",): (
        "confirm",
        "log",
        "review",
        "outcome",
        "size",
        "backtest-swing",
        "tune-swing",
        "tuning-status",
        "review-tuning-swing",
        "validate-tuning-patch",
        "apply-tuning-patch",
        "backtest-intraday",
        "migrate-journal",
    ),
    ("trade", "review"): ("intraday", "swing"),
    ("strategy",): ("skill", "init", "validate", "list", "create", "backtest"),
    ("strategy", "skill"): ("generate", "check", "index"),
}

EXACT_COMMANDS: dict[tuple[str, ...], tuple[str, ...]] = EXPECTED_COMMANDS | {
    (): (*EXPECTED_COMMANDS[()], "version"),
}


REMOVED_PATHS: tuple[tuple[str, ...], ...] = (
    ("data",),
    ("skill",),
    ("update",),
    ("stockbit",),
    ("universe",),
    ("broker",),
    ("chart",),
    ("status",),
    ("trade", "swing"),
    ("trade", "intraday"),
    ("trade", "opening"),
    ("trade", "review", "pre-open"),
    ("analyze", "signal-audit"),
    ("analyze", "signal-backfill-observations"),
    ("analyze", "signal-labels"),
    ("analyze", "signal-replay"),
    ("analyze", "signal-readiness"),
    ("analyze", "accum-audit"),
    ("analyze", "signal-inspect"),
)


HELP_PATHS: tuple[tuple[str, ...], ...] = (
    (),
    ("audit",),
    ("audit", "data"),
    ("audit", "data", "manifest"),
    ("audit", "data", "source-contracts"),
    ("audit", "data", "reconcile-sources"),
    ("audit", "data", "contract-gate"),
    ("audit", "data", "seasonality-cleanup-plan"),
    ("audit", "data", "repair-seasonality-cache"),
    ("audit", "data", "candidate-observation-identity"),
    ("audit", "data", "repair-candidate-observations"),
    ("fetch",),
    ("fetch", "market"),
    ("fetch", "broker"),
    ("fetch", "broker-import"),
    ("fetch", "broker-history"),
    ("fetch", "broker-top-foreign"),
    ("fetch", "stockbit"),
    ("fetch", "stockbit", "login"),
    ("fetch", "stockbit", "status"),
    ("fetch", "stockbit", "spy"),
    ("fetch", "stockbit", "test"),
    ("fetch", "stockbit", "browse"),
    ("fetch", "stockbit", "fetch-top5"),
    ("fetch", "universe"),
    ("fetch", "universe", "list"),
    ("fetch", "universe", "update"),
    ("fetch", "universe", "inspect"),
    ("fetch", "universe", "create"),
    ("fetch", "status"),
    ("fetch", "enrichment-history"),
    ("screen",),
    ("screen", "pre-open"),
    ("screen", "accum"),
    ("screen", "watchlist"),
    ("screen", "compare"),
    ("learn",),
    ("research",),
    ("research", "signal"),
    ("research", "signal", "backfill"),
    ("research", "signal", "capture"),
    ("research", "signal", "labels"),
    ("research", "signal", "replay"),
    ("research", "signal", "readiness"),
    ("research", "accumulation"),
    ("research", "accumulation", "evaluate"),
    ("indicator",),
    ("analyze",),
    ("analyze", "swing"),
    ("analyze", "signal"),
    ("analyze", "signal", "inspect"),
    ("analyze", "chart"),
    ("trade",),
    ("trade", "log"),
    ("trade", "review"),
    ("trade", "size"),
    ("trade", "backtest-swing"),
    ("trade", "tune-swing"),
    ("trade", "tuning-status"),
    ("trade", "review-tuning-swing"),
    ("trade", "validate-tuning-patch"),
    ("trade", "apply-tuning-patch"),
    ("trade", "backtest-intraday"),
    ("view",),
    ("view", "universe"),
    ("view", "broker"),
    ("view", "broker", "flow"),
    ("view", "broker", "top"),
    ("view", "broker", "history"),
    ("view", "broker", "top-foreign"),
    ("strategy",),
    ("strategy", "skill"),
)


REMOVED_HELP_SNIPPETS: tuple[str, ...] = (
    "saham data",
    "saham skill",
    "saham trade swing",
    "saham trade intraday",
    "saham swing",
    "saham intraday",
    "saham trade log pre-open",
    "saham trade review pre-open",
    "saham screen pre-open-log",
    "saham screen pre-open-review",
    "saham update",
    "saham stockbit",
    "saham universe",
    "saham broker",
    "saham chart",
    "saham status",
    "broker fetch",
    "saham analyze signal-audit",
    "saham analyze signal-backfill-observations",
    "saham analyze signal-labels",
    "saham analyze signal-replay",
    "saham analyze signal-readiness",
    "saham analyze signal-inspect",
    "saham analyze accum-audit",
)


REMOVED_ADAPTER_FILES: tuple[str, ...] = (
    "src/adapters/cli/data_commands.py",
    "src/adapters/cli/update_commands.py",
    "src/adapters/cli/opening_commands.py",
    "src/adapters/cli/screen_commands.py",
    "src/adapters/cli/analyze_regime_display.py",
    "src/adapters/cli/analyze_signal_audit_commands.py",
)


REMOVED_TEST_FILES: tuple[str, ...] = (
    "tests/adapters/cli/test_update_commands.py",
    "tests/adapters/cli/test_screen_commands.py",
    "tests/adapters/cli/test_analyze_signal_audit_commands.py",
    "tests/application/use_case/test_assess_signal.py",
    "tests/application/use_case/test_signal_baseline.py",
    "tests/application/use_case/test_audit_signal_use_case.py",
    "tests/application/services/test_signal_evidence_builder.py",
)

REMOVED_SOURCE_REFERENCE_PATTERNS: tuple[str, ...] = (
    "src.adapters.cli.data_commands",
    "src.adapters.cli.update_commands",
    "src.adapters.cli.opening_commands",
    "src.adapters.cli.screen_commands",
    "src.adapters.cli.analyze_regime_display",
    "src.application.use_case.market_regime_use_case",
    "src.adapters.cli.analyze_signal_audit_commands",
    "src.application.use_case.assess_signal_use_case",
    "src.application.use_case.audit_signal_use_case",
    "src.application.services.signal_evidence_builder",
    "src.application.services.engine_bootstrap.signal_weight_config_resolver",
    "src.domain.value_objects.signal_audit",
    "data_commands.py",
    "update_commands.py",
    "opening_commands.py",
    "screen_commands.py",
    "analyze_regime_display.py",
    "market_regime_use_case.py",
    "test_update_commands.py",
    "test_screen_commands.py",
    "analyze_signal_audit_commands.py",
    "assess_signal_use_case.py",
    "audit_signal_use_case.py",
    "signal_evidence_builder.py",
    "signal_weight_config_resolver.py",
    "test_assess_signal.py",
    "test_signal_baseline.py",
    "test_audit_signal_use_case.py",
    "test_signal_evidence_builder.py",
    "test_analyze_signal_audit_commands.py",
)


def _listed_commands(help_text: str) -> tuple[str, ...]:
    commands: list[str] = []
    in_commands = False
    for line in help_text.splitlines():
        if " Commands " in line:
            in_commands = True
            continue
        if in_commands and line.startswith("╰"):
            break
        if not in_commands:
            continue
        match = re.match(r"^│\s+([a-z][\w-]*)\s{2,}", line)
        if match:
            commands.append(match.group(1))
    return tuple(commands)


def test_public_command_tree_contract():
    for path, expected in EXPECTED_COMMANDS.items():
        result = runner.invoke(app, [*path, "--help"])

        assert result.exit_code == 0, path
        for command in expected:
            assert command in result.stdout, path


def test_public_command_tree_has_no_extra_commands():
    for path, expected in EXACT_COMMANDS.items():
        result = runner.invoke(app, [*path, "--help"])

        assert result.exit_code == 0, path
        assert set(_listed_commands(result.stdout)) == set(expected), path


def test_signal_labels_help_exposes_batch_generation_flags():
    result = runner.invoke(app, ["research", "signal", "labels", "--help"])

    assert result.exit_code == 0
    assert "--generate-all" in result.stdout
    assert "--eligible-dates" in result.stdout


def test_signal_inspect_help_exposes_date_and_format_options():
    result = runner.invoke(app, ["analyze", "signal", "inspect", "--help"])

    assert result.exit_code == 0
    assert "--date" in result.stdout
    assert "--format" in result.stdout
    assert "--window-days" in result.stdout


def test_signal_readiness_help_exposes_target_option():
    result = runner.invoke(app, ["research", "signal", "readiness", "--help"])

    assert result.exit_code == 0
    assert "--target" in result.stdout


def test_signal_backfill_observations_help_exposes_required_options():
    result = runner.invoke(app, ["research", "signal", "backfill", "--help"])

    assert result.exit_code == 0
    assert "--universe" in result.stdout
    assert "--start" in result.stdout
    assert "--end" in result.stdout
    assert "--generate-labels" in result.stdout


def test_signal_capture_help_exposes_contract_and_session_options():
    result = runner.invoke(app, ["research", "signal", "capture", "--help"])

    assert result.exit_code == 0
    assert "--universe" in result.stdout
    assert "--session" in result.stdout
    assert "--contract" in result.stdout
    assert "candidate_observations" in result.stdout
    assert "signal_forward_labels" in result.stdout


def test_removed_legacy_paths_stay_removed():
    for path in REMOVED_PATHS:
        result = runner.invoke(app, [*path, "--help"])

        assert result.exit_code != 0, path


def test_active_help_does_not_advertise_removed_paths():
    for path in HELP_PATHS:
        result = runner.invoke(app, [*path, "--help"])

        assert result.exit_code == 0, path
        for snippet in REMOVED_HELP_SNIPPETS:
            assert snippet not in result.stdout, (path, snippet)


def test_removed_legacy_adapter_files_stay_removed():
    for path in REMOVED_ADAPTER_FILES:
        assert not (REPO_ROOT / path).exists(), path


def test_removed_legacy_test_files_stay_removed():
    for path in REMOVED_TEST_FILES:
        assert not (REPO_ROOT / path).exists(), path


def test_lifecycle_routers_import_expected_command_modules():
    assert screen_lifecycle_commands.pre_open is screen_pre_open_commands.pre_open
    assert fetch_commands.collect_iev is fetch_iev_commands.collect_iev

    assert trade_commands.confirm_open is trade_intraday_commands.confirm_open
    assert trade_commands.confirm_review is trade_intraday_commands.confirm_review
    assert trade_commands.confirm_outcome is trade_intraday_commands.confirm_outcome
    assert trade_commands.intraday_backtest is trade_intraday_commands.intraday_backtest


def test_active_source_and_tests_do_not_reference_removed_modules():
    search_roots = (REPO_ROOT / "src", REPO_ROOT / "tests")
    ignored_files = {Path(__file__).resolve()}
    violations: list[tuple[str, str]] = []

    for root in search_roots:
        for path in root.rglob("*.py"):
            if path in ignored_files or "__pycache__" in path.parts:
                continue
            text = path.read_text()
            for pattern in REMOVED_SOURCE_REFERENCE_PATTERNS:
                if pattern in text:
                    violations.append((str(path.relative_to(REPO_ROOT)), pattern))

    assert violations == []
