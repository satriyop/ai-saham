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
        "fetch",
        "screen",
        "learn",
        "view",
        "indicator",
        "analyze",
        "strategy",
        "trade",
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
    ),
    ("fetch", "stockbit"): ("login", "status", "spy", "test", "browse", "fetch-top5"),
    ("fetch", "universe"): ("list", "update", "inspect"),
    ("screen",): ("pre-open", "accum"),
    ("learn",): ("snapshot", "track", "grade", "prompt", "tune"),
    ("indicator",): ("compute", "snapshot", "create", "list", "show", "delete"),
    ("analyze",): (
        "risk",
        "compare",
        "sentiment",
        "audit",
        "regime",
        "swing",
        "accum-audit",
        "swing-compare",
        "chart",
    ),
    ("analyze", "chart"): ("price", "rsi", "volume"),
    ("view",): ("broker",),
    ("view", "broker"): ("status", "flow", "top", "history", "top-foreign", "mappings"),
    ("trade",): (
        "confirm",
        "log",
        "review",
        "outcome",
        "size",
        "backtest-swing",
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
)


HELP_PATHS: tuple[tuple[str, ...], ...] = (
    (),
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
    ("fetch", "status"),
    ("screen",),
    ("screen", "pre-open"),
    ("screen", "accum"),
    ("learn",),
    ("indicator",),
    ("analyze",),
    ("analyze", "swing"),
    ("analyze", "chart"),
    ("trade",),
    ("trade", "log"),
    ("trade", "review"),
    ("trade", "size"),
    ("trade", "backtest-swing"),
    ("trade", "backtest-intraday"),
    ("view",),
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
)


REMOVED_ADAPTER_FILES: tuple[str, ...] = (
    "src/adapters/cli/data_commands.py",
    "src/adapters/cli/update_commands.py",
    "src/adapters/cli/opening_commands.py",
    "src/adapters/cli/screen_commands.py",
)


REMOVED_TEST_FILES: tuple[str, ...] = (
    "tests/adapters/cli/test_update_commands.py",
    "tests/adapters/cli/test_screen_commands.py",
)

REMOVED_SOURCE_REFERENCE_PATTERNS: tuple[str, ...] = (
    "src.adapters.cli.data_commands",
    "src.adapters.cli.update_commands",
    "src.adapters.cli.opening_commands",
    "src.adapters.cli.screen_commands",
    "data_commands.py",
    "update_commands.py",
    "opening_commands.py",
    "screen_commands.py",
    "test_update_commands.py",
    "test_screen_commands.py",
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
