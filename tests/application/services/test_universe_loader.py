from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.services.universe_loader import resolve_tickers


def test_resolve_tickers_cached_with_repository():
    fake_repo = MagicMock()
    fake_repo.get_cached_tickers.return_value = ["BBCA", "BBRI"]

    loader = MagicMock()

    tickers = resolve_tickers(
        universe="cached",
        explicit=[],
        db_path=Path("dummy.db"),
        loader=loader,
        repository=fake_repo,
    )

    assert tickers == ["BBCA", "BBRI"]
    fake_repo.get_cached_tickers.assert_called_once()


def test_resolve_tickers_cached_without_repository_raises_value_error():
    loader = MagicMock()

    with pytest.raises(ValueError) as exc_info:
        resolve_tickers(
            universe="cached",
            explicit=[],
            db_path=Path("dummy.db"),
            loader=loader,
            repository=None,
        )

    assert "BrokerDataRepository is required when universe='cached'" in str(exc_info.value)
