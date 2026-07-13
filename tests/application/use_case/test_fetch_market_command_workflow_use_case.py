from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.application.services.fetch_market_provider_precondition import (
    FetchMarketProviderPrecondition,
)
from src.application.services.market_freshness_service import MarketFreshnessService
from src.application.use_case.fetch_market_command_workflow_use_case import (
    FetchMarketCommandStartEvent,
    FetchMarketCommandWorkflowRequest,
    FetchMarketCommandWorkflowUseCase,
    FetchMarketStatusHeader,
)
from src.application.use_case.fetch_market_refresh_use_case import (
    BrokerFetchResult,
    FetchMarketRefreshResponse,
    FetchMarketRefreshUseCase,
    FetchMarketTickerResult,
)
from src.application.use_case.refresh_market_context_inputs_use_case import (
    RefreshMarketContextInputsResponse,
)


@pytest.fixture
def mock_refresh_use_case():
    return Mock(spec=FetchMarketRefreshUseCase)


@pytest.fixture
def mock_provider_precondition():
    precond = Mock(spec=FetchMarketProviderPrecondition)
    precond.validate.return_value = None
    return precond


@pytest.fixture
def mock_market_freshness():
    freshness = Mock(spec=MarketFreshnessService)
    freshness.resolve_reference_trading_day.return_value = date(2026, 7, 13)
    return freshness


def test_no_tickers_raises_value_error(
    mock_refresh_use_case,
    mock_provider_precondition,
    mock_market_freshness,
):
    mock_resolver = Mock(return_value=[])

    # Construct usecase
    use_case = FetchMarketCommandWorkflowUseCase(
        refresh_use_case=mock_refresh_use_case,
        provider_precondition=mock_provider_precondition,
        non_idx_tickers_loader=lambda: frozenset(),
        market_status_loader=lambda: FetchMarketStatusHeader("Open", True),
        calendar_refresh=lambda *_: "cached",
        context_refresh=lambda *_: RefreshMarketContextInputsResponse(statuses=()),
        market_freshness=mock_market_freshness,
        ticker_resolver=mock_resolver,
    )

    req = FetchMarketCommandWorkflowRequest(
        tickers=[],
        universe="empty",
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    with pytest.raises(ValueError, match="No tickers to update"):
        use_case.execute(req)

    mock_resolver.assert_called_once_with("empty", [], Path("dummy.db"))


def test_provider_precondition_runs_before_refresh_and_fails(
    mock_refresh_use_case,
    mock_provider_precondition,
    mock_market_freshness,
):
    mock_resolver = Mock(return_value=["BBCA"])
    mock_provider_precondition.validate.return_value = "Precondition error details"

    use_case = FetchMarketCommandWorkflowUseCase(
        refresh_use_case=mock_refresh_use_case,
        provider_precondition=mock_provider_precondition,
        non_idx_tickers_loader=lambda: frozenset(),
        market_status_loader=lambda: FetchMarketStatusHeader("Open", True),
        calendar_refresh=lambda *_: "cached",
        context_refresh=lambda *_: RefreshMarketContextInputsResponse(statuses=()),
        market_freshness=mock_market_freshness,
        ticker_resolver=mock_resolver,
    )

    req = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    with pytest.raises(ValueError, match="Precondition error details"):
        use_case.execute(req)

    mock_resolver.assert_called_once_with(None, ["BBCA"], Path("dummy.db"))
    # Refresh must not have been executed
    mock_refresh_use_case.execute.assert_not_called()


def test_broker_only_skips_precondition_and_context_refresh(
    mock_refresh_use_case,
    mock_provider_precondition,
    mock_market_freshness,
):
    mock_resolver = Mock(return_value=["BBCA"])
    mock_refresh_use_case.execute.return_value = FetchMarketRefreshResponse(
        ticker_list=["IHSG", "BBCA"],
        stock_tickers_only=["BBCA"],
        ticker_results=[],
        ok_count=1,
        fail_count=0,
    )

    context_refresh = Mock(return_value=RefreshMarketContextInputsResponse(statuses=()))

    use_case = FetchMarketCommandWorkflowUseCase(
        refresh_use_case=mock_refresh_use_case,
        provider_precondition=mock_provider_precondition,
        non_idx_tickers_loader=lambda: frozenset(),
        market_status_loader=lambda: FetchMarketStatusHeader("Open", True),
        calendar_refresh=lambda *_: "cached",
        context_refresh=context_refresh,
        market_freshness=mock_market_freshness,
        ticker_resolver=mock_resolver,
    )

    req = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=True,  # broker_only = True
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    res = use_case.execute(req)

    mock_resolver.assert_called_once_with(None, ["BBCA"], Path("dummy.db"))
    # validate must NOT be called on provider_precondition
    mock_provider_precondition.validate.assert_not_called()

    # context_refresh must NOT be called
    context_refresh.assert_not_called()

    assert res.response.ok_count == 1


def test_calendar_skip_priority_and_call_count(
    mock_refresh_use_case,
    mock_provider_precondition,
    mock_market_freshness,
):
    mock_resolver = Mock(return_value=["BBCA"])
    mock_refresh_use_case.execute.return_value = FetchMarketRefreshResponse(
        ticker_list=["IHSG", "BBCA"],
        stock_tickers_only=["BBCA"],
        ticker_results=[],
        ok_count=1,
        fail_count=0,
    )

    calendar_refresh = Mock(return_value="stockbit_synced")

    use_case = FetchMarketCommandWorkflowUseCase(
        refresh_use_case=mock_refresh_use_case,
        provider_precondition=mock_provider_precondition,
        non_idx_tickers_loader=lambda: frozenset(),
        market_status_loader=lambda: FetchMarketStatusHeader("Open", True),
        calendar_refresh=calendar_refresh,
        context_refresh=lambda *_: RefreshMarketContextInputsResponse(statuses=()),
        market_freshness=mock_market_freshness,
        ticker_resolver=mock_resolver,
    )

    # Case A: no_calendar=True wins over no_enrichment=True
    req_a = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=True,
        no_calendar=True,
    )
    res_a = use_case.execute(req_a)
    assert res_a.calendar_status == "skip:--no-calendar"
    calendar_refresh.assert_not_called()

    # Case B: no_enrichment=True skips
    req_b = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=True,
        no_calendar=False,
    )
    res_b = use_case.execute(req_b)
    assert res_b.calendar_status == "skip:--no-enrichment"
    calendar_refresh.assert_not_called()

    # Case C: non-stockbit skips
    req_c = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="idx",  # IDX instead of stockbit
        refresh=False,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    res_c = use_case.execute(req_c)
    assert res_c.calendar_status == "skip:no-stockbit"
    calendar_refresh.assert_not_called()

    # Case D: Calendar called exactly once for eligible Stockbit run
    fake_broker = Mock()
    fake_broker.api_client = object()
    req_d = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=fake_broker,
        broker_provider_name="stockbit",
        refresh=True,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    res_d = use_case.execute(req_d)
    assert res_d.calendar_status == "stockbit_synced"
    calendar_refresh.assert_called_once_with(Path("dummy.db"), fake_broker.api_client, True)


def test_context_refresh_runs_only_when_not_broker_only(
    mock_refresh_use_case,
    mock_provider_precondition,
    mock_market_freshness,
):
    mock_resolver = Mock(return_value=["BBCA"])
    mock_refresh_use_case.execute.return_value = FetchMarketRefreshResponse(
        ticker_list=["IHSG", "BBCA"],
        stock_tickers_only=["BBCA"],
        ticker_results=[],
        ok_count=1,
        fail_count=0,
    )

    context_refresh = Mock(
        return_value=RefreshMarketContextInputsResponse(statuses=("vix:cached",))
    )

    use_case = FetchMarketCommandWorkflowUseCase(
        refresh_use_case=mock_refresh_use_case,
        provider_precondition=mock_provider_precondition,
        non_idx_tickers_loader=lambda: frozenset(),
        market_status_loader=lambda: FetchMarketStatusHeader("Open", True),
        calendar_refresh=lambda *_: "cached",
        context_refresh=context_refresh,
        market_freshness=mock_market_freshness,
        ticker_resolver=mock_resolver,
    )

    req = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=False,  # Not broker_only
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    res = use_case.execute(req)

    mock_resolver.assert_called_once_with(None, ["BBCA"], Path("dummy.db"))
    context_refresh.assert_called_once_with(Path("dummy.db"), 30)
    assert res.context_statuses == ("vix:cached",)


def test_expected_trading_day_comes_from_freshness_service(
    mock_refresh_use_case,
    mock_provider_precondition,
    mock_market_freshness,
):
    mock_resolver = Mock(return_value=["BBCA"])
    mock_refresh_use_case.execute.return_value = FetchMarketRefreshResponse(
        ticker_list=["IHSG", "BBCA"],
        stock_tickers_only=["BBCA"],
        ticker_results=[],
        ok_count=1,
        fail_count=0,
    )

    use_case = FetchMarketCommandWorkflowUseCase(
        refresh_use_case=mock_refresh_use_case,
        provider_precondition=mock_provider_precondition,
        non_idx_tickers_loader=lambda: frozenset(),
        market_status_loader=lambda: FetchMarketStatusHeader("Open", True),
        calendar_refresh=lambda *_: "cached",
        context_refresh=lambda *_: RefreshMarketContextInputsResponse(statuses=()),
        market_freshness=mock_market_freshness,
        ticker_resolver=mock_resolver,
    )

    req = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    res = use_case.execute(req)

    mock_resolver.assert_called_once_with(None, ["BBCA"], Path("dummy.db"))
    mock_market_freshness.resolve_reference_trading_day.assert_called_once()
    assert res.expected_trading_day == date(2026, 7, 13)


def test_market_status_loader_called_once(
    mock_refresh_use_case,
    mock_provider_precondition,
    mock_market_freshness,
):
    mock_resolver = Mock(return_value=["BBCA"])
    mock_refresh_use_case.execute.return_value = FetchMarketRefreshResponse(
        ticker_list=["IHSG", "BBCA"],
        stock_tickers_only=["BBCA"],
        ticker_results=[],
        ok_count=1,
        fail_count=0,
    )

    status_loader = Mock(return_value=FetchMarketStatusHeader("Closed", False))

    use_case = FetchMarketCommandWorkflowUseCase(
        refresh_use_case=mock_refresh_use_case,
        provider_precondition=mock_provider_precondition,
        non_idx_tickers_loader=lambda: frozenset(),
        market_status_loader=status_loader,
        calendar_refresh=lambda *_: "cached",
        context_refresh=lambda *_: RefreshMarketContextInputsResponse(statuses=()),
        market_freshness=mock_market_freshness,
        ticker_resolver=mock_resolver,
    )

    req = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    res = use_case.execute(req)

    mock_resolver.assert_called_once_with(None, ["BBCA"], Path("dummy.db"))
    status_loader.assert_called_once()
    assert res.header is not None
    assert res.header.line == "Closed"
    assert res.header.is_open is False


def test_per_ticker_callback_and_on_start_received(
    mock_refresh_use_case,
    mock_provider_precondition,
    mock_market_freshness,
):
    mock_resolver = Mock(return_value=["BBCA"])
    ticker_res = FetchMarketTickerResult(
        ticker="BBCA",
        candles_status="cached",
        broker_result=BrokerFetchResult("cached", "cached"),
        meta_status="cached",
        enrichment_status="cached",
        any_error=False,
        all_cached=True,
    )

    # Set up execute implementation to call on_ticker_complete
    def fake_execute(request, on_ticker_complete=None):
        if on_ticker_complete:
            on_ticker_complete(ticker_res, 1, 2)
        return FetchMarketRefreshResponse(
            ticker_list=["IHSG", "BBCA"],
            stock_tickers_only=["BBCA"],
            ticker_results=[ticker_res],
            ok_count=1,
            fail_count=0,
        )

    mock_refresh_use_case.execute.side_effect = fake_execute

    use_case = FetchMarketCommandWorkflowUseCase(
        refresh_use_case=mock_refresh_use_case,
        provider_precondition=mock_provider_precondition,
        non_idx_tickers_loader=lambda: frozenset(),
        market_status_loader=lambda: FetchMarketStatusHeader("Open", True),
        calendar_refresh=lambda *_: "cached",
        context_refresh=lambda *_: RefreshMarketContextInputsResponse(statuses=()),
        market_freshness=mock_market_freshness,
        ticker_resolver=mock_resolver,
    )

    on_start = Mock()
    on_ticker_complete = Mock()

    req = FetchMarketCommandWorkflowRequest(
        tickers=["BBCA"],
        universe=None,
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    use_case.execute(req, on_ticker_complete=on_ticker_complete, on_start=on_start)

    mock_resolver.assert_called_once_with(None, ["BBCA"], Path("dummy.db"))
    on_start.assert_called_once()
    start_event = on_start.call_args[0][0]
    assert isinstance(start_event, FetchMarketCommandStartEvent)
    assert start_event.ticker_count == 2
    assert start_event.days == 30

    on_ticker_complete.assert_called_once_with(ticker_res, 1, 2)


def test_inner_refresh_receives_universe_none(
    mock_refresh_use_case,
    mock_provider_precondition,
    mock_market_freshness,
):
    mock_resolver = Mock(return_value=["BBCA"])
    mock_refresh_use_case.execute.return_value = FetchMarketRefreshResponse(
        ticker_list=["IHSG", "BBCA"],
        stock_tickers_only=["BBCA"],
        ticker_results=[],
        ok_count=1,
        fail_count=0,
    )

    use_case = FetchMarketCommandWorkflowUseCase(
        refresh_use_case=mock_refresh_use_case,
        provider_precondition=mock_provider_precondition,
        non_idx_tickers_loader=lambda: frozenset(),
        market_status_loader=lambda: FetchMarketStatusHeader("Open", True),
        calendar_refresh=lambda *_: "cached",
        context_refresh=lambda *_: RefreshMarketContextInputsResponse(statuses=()),
        market_freshness=mock_market_freshness,
        ticker_resolver=mock_resolver,
    )

    req = FetchMarketCommandWorkflowRequest(
        tickers=[],
        universe="lq45",
        days=30,
        db_path=Path("dummy.db"),
        candles_provider="yahoo",
        broker_provider=Mock(),
        broker_provider_name="stockbit",
        refresh=False,
        candles_only=False,
        broker_only=False,
        no_meta=False,
        no_enrichment=False,
        no_calendar=False,
    )
    use_case.execute(req)

    mock_resolver.assert_called_once_with("lq45", [], Path("dummy.db"))
    # Assert that the inner refresh execute is called with universe=None
    called_request = mock_refresh_use_case.execute.call_args[0][0]
    assert called_request.universe is None
    assert called_request.tickers == ["IHSG", "BBCA"]
