"""
Tests for fetch status CLI command -- DB path resolution.

Layer: Adapter
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

import src.adapters.cli.fetch_status_commands as status_commands


@dataclass(frozen=True)
class FakeStorageConfig:
    db_path: str = "data/db/data.db"


@dataclass(frozen=True)
class FakeAppConfig:
    storage: FakeStorageConfig = FakeStorageConfig()


_captured_paths: List[Path] = []


class SpyProviderFactory:
    """Replacement for SQLiteSystemStatusProvider that records the db_path."""

    captured_paths: List[Path] = []

    def __new__(cls, db_path: Path):
        cls.captured_paths.append(db_path)
        return super().__new__(cls)

    def check_provider_health(self) -> List:
        return []

    def get_data_freshness(self) -> List:
        return []


def _fake_use_case(provider) -> object:
    """Return a use case stub that ignores provider and returns empty response."""
    return type(
        "FakeUC",
        (),
        {
            "execute": lambda self: type(
                "FakeResp",
                (),
                {"providers": [], "freshness": []},
            )()
        },
    )()


class TestDefaultDbPath:
    def test_default_path_comes_from_app_config(self, monkeypatch, tmp_path: Path):
        configured_path = tmp_path / "configured.db"
        monkeypatch.setattr(
            status_commands,
            "load_app_config",
            lambda: FakeAppConfig(storage=FakeStorageConfig(db_path=str(configured_path))),
        )

        SpyProviderFactory.captured_paths.clear()
        monkeypatch.setattr(status_commands, "SQLiteSystemStatusProvider", SpyProviderFactory)
        monkeypatch.setattr(status_commands, "GetSystemStatusUseCase", _fake_use_case)

        status_commands.status(db_path=None)

        assert len(SpyProviderFactory.captured_paths) == 1
        assert SpyProviderFactory.captured_paths[0] == configured_path

    def test_explicit_db_path_wins(self, monkeypatch, tmp_path: Path):
        def raise_on_load(*args, **kwargs):
            raise RuntimeError("load_app_config should not be called")

        monkeypatch.setattr(status_commands, "load_app_config", raise_on_load)

        SpyProviderFactory.captured_paths.clear()
        monkeypatch.setattr(status_commands, "SQLiteSystemStatusProvider", SpyProviderFactory)
        monkeypatch.setattr(status_commands, "GetSystemStatusUseCase", _fake_use_case)

        explicit_path = tmp_path / "explicit.db"
        status_commands.status(db_path=explicit_path)

        assert len(SpyProviderFactory.captured_paths) == 1
        assert SpyProviderFactory.captured_paths[0] == explicit_path

    def test_missing_db_message_uses_configured_path(self, monkeypatch, tmp_path: Path, capsys):
        configured_path = tmp_path / "nonexistent" / "app_configured.sqlite"
        monkeypatch.setattr(
            status_commands,
            "load_app_config",
            lambda: FakeAppConfig(storage=FakeStorageConfig(db_path=str(configured_path))),
        )

        monkeypatch.setattr(status_commands, "GetSystemStatusUseCase", _fake_use_case)

        status_commands.status(db_path=None)

        out = capsys.readouterr().out
        assert configured_path.name in out
        assert "data.db" not in out
