"""Tests for RefreshStockbitEnrichmentUseCase — no infrastructure imports needed."""

from src.application.use_case.refresh_stockbit_enrichment import (
    EnrichmentTask,
    RefreshStockbitEnrichmentRequest,
    RefreshStockbitEnrichmentUseCase,
)


def _task(label: str, *, fresh: bool, raises: bool = False) -> EnrichmentTask:
    def is_fresh() -> bool:
        return fresh

    def fetch() -> None:
        if raises:
            raise RuntimeError(f"{label} fetch failed")

    return EnrichmentTask(label=label, is_fresh=is_fresh, fetch=fetch)


def _uc() -> RefreshStockbitEnrichmentUseCase:
    return RefreshStockbitEnrichmentUseCase()


def test_all_cached_returns_check_mark_format():
    tasks = [_task(lbl, fresh=True) for lbl in ["notation", "analyst", "bandar"]]
    resp = _uc().execute(RefreshStockbitEnrichmentRequest(ticker="BBCA", tasks=tasks))
    assert resp.status == "✓(notation,analyst,bandar)"
    assert resp.cached == ("notation", "analyst", "bandar")
    assert resp.fetched == ()
    assert resp.errors == ()


def test_some_fetched_returns_plus_joined_with_cached_suffix():
    tasks = [
        _task("notation", fresh=False),
        _task("analyst",  fresh=False),
        _task("insider",  fresh=True),
        _task("season",   fresh=True),
    ]
    resp = _uc().execute(RefreshStockbitEnrichmentRequest(ticker="BBCA", tasks=tasks))
    assert resp.status == "notation+analyst  ✓(insider,season)"
    assert resp.fetched == ("notation", "analyst")
    assert resp.cached == ("insider", "season")


def test_all_fetched_returns_plus_joined_without_cached_suffix():
    tasks = [_task(lbl, fresh=False) for lbl in ["bandar", "fundam"]]
    resp = _uc().execute(RefreshStockbitEnrichmentRequest(ticker="BBCA", tasks=tasks))
    assert resp.status == "bandar+fundam"
    assert resp.fetched == ("bandar", "fundam")
    assert resp.cached == ()


def test_error_on_one_task_returns_err_prefix_and_continues_others():
    tasks = [
        _task("notation", fresh=False, raises=True),
        _task("analyst",  fresh=False),
        _task("bandar",   fresh=True),
    ]
    resp = _uc().execute(RefreshStockbitEnrichmentRequest(ticker="BBCA", tasks=tasks))
    assert resp.status.startswith("ERR:")
    assert "notation" in resp.status
    assert resp.fetched == ("analyst",)
    assert resp.cached == ("bandar",)
    assert len(resp.errors) == 1
    assert resp.errors[0].startswith("notation:")
