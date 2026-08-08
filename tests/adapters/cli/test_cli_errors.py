"""CLI error taxonomy and exit-code contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from src.adapters.cli.cli_errors import (
    EXIT_DATA,
    EXIT_OK,
    EXIT_USER,
    CliErrorCategory,
    echo_cli_empty,
    echo_cli_error,
    raise_cli_error,
    raise_data_unavailable,
    raise_user_error,
    resolve_cli_db_path,
)

runner = CliRunner()


def test_exit_code_constants() -> None:
    assert EXIT_OK == 0
    assert EXIT_USER == 1
    assert EXIT_DATA == 2


def test_echo_cli_error_includes_category(capsys) -> None:
    echo_cli_error("boom", category=CliErrorCategory.USER_INPUT, tip="try again")
    err = capsys.readouterr().err
    assert "Error [user_input]: boom" in err
    assert "Tip: try again" in err


def test_echo_cli_empty_is_not_error_prefix(capsys) -> None:
    echo_cli_empty("No candidates found.", next_step="saham fetch market --universe lq45")
    out = capsys.readouterr()
    assert "Error" not in out.out
    assert "No candidates found." in out.out
    assert "Next: saham fetch market" in out.out


def test_raise_user_error_exits_1() -> None:
    with pytest.raises(typer.Exit) as ei:
        raise_user_error("bad ticker")
    assert ei.value.exit_code == EXIT_USER


def test_raise_data_unavailable_exits_2() -> None:
    with pytest.raises(typer.Exit) as ei:
        raise_data_unavailable("no cache")
    assert ei.value.exit_code == EXIT_DATA


def test_raise_cli_error_internal_defaults_to_user_exit() -> None:
    with pytest.raises(typer.Exit) as ei:
        raise_cli_error("unexpected", category=CliErrorCategory.INTERNAL)
    assert ei.value.exit_code == EXIT_USER


def test_resolve_explicit_db_missing_exits_and_does_not_create(tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "missing.db"
    assert not missing.exists()
    with pytest.raises(typer.Exit) as ei:
        resolve_cli_db_path(missing, configured_default=tmp_path / "default.db")
    assert ei.value.exit_code == EXIT_USER
    assert not missing.exists()
    assert not missing.parent.exists()


def test_resolve_explicit_db_existing(tmp_path: Path) -> None:
    db = tmp_path / "data.db"
    db.write_bytes(b"")
    resolved = resolve_cli_db_path(db, configured_default=tmp_path / "other.db")
    assert resolved == db.resolve()


def test_resolve_default_may_be_missing(tmp_path: Path) -> None:
    default = tmp_path / "will_create_later.db"
    assert not default.exists()
    resolved = resolve_cli_db_path(None, configured_default=default)
    assert resolved == default
    assert not default.exists()


def test_resolve_explicit_db_directory_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "not_a_file"
    directory.mkdir()
    with pytest.raises(typer.Exit) as ei:
        resolve_cli_db_path(directory, configured_default=tmp_path / "default.db")
    assert ei.value.exit_code == EXIT_USER
