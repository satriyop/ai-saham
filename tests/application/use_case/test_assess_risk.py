"""
Tests for AssessRisk use case.

These tests use mock repository to verify:
- Use case orchestration (indicators + rule evaluation)
- Request/response DTOs
- Error handling
- Integration with RuleEngine

All tests run offline with no external dependencies.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.use_case.assess_risk_use_case import (
    AssessAllProfilesResponse,
    AssessRiskRequest,
    AssessRiskResponse,
    AssessRiskUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.risk_signal import RiskProfile

# --- Test Fixtures ---


def make_candle(ticker: str, days_ago: int, price: str = "100.00") -> Candle:
    """Create a test candle with consistent prices."""
    return Candle(
        ticker=ticker,
        date=date.today() - timedelta(days=days_ago),
        open=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        close=Decimal(price),
        volume=100000,
    )


def make_trending_candles(
    ticker: str, count: int, start_price: float = 100.0, trend: float = 1.0
) -> list[Candle]:
    """Create candles with a price trend for realistic indicator testing."""
    candles = []
    for i in range(count - 1, -1, -1):
        price = Decimal(str(start_price + (count - 1 - i) * trend))
        candles.append(
            Candle(
                ticker=ticker,
                date=date.today() - timedelta(days=i),
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price,
                volume=100000,
            )
        )
    return candles


class MockRepository(MarketDataRepository):
    """Mock repository for testing."""

    def __init__(self, candles: list[Candle] | None = None):
        self._candles = candles or []

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        filtered = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date:
            filtered = [c for c in filtered if c.date >= start_date]
        if end_date:
            filtered = [c for c in filtered if c.date <= end_date]
        return sorted(filtered, key=lambda c: c.date)

    def save_candles(self, candles: list[Candle]) -> None:
        pass

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        return len(self._candles) > 0

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        filtered = [c for c in self._candles if c.ticker == ticker.upper()]
        if not filtered:
            return None
        sorted_candles = sorted(filtered, key=lambda c: c.date)
        return (sorted_candles[0].date, sorted_candles[-1].date)


# --- Tests ---


class TestAssessRiskUseCase:
    """Test AssessRiskUseCase behavior."""

    def test_execute_returns_risk_assessment(self):
        """Should return a RiskAssessment for valid ticker."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA", sensitivity="balanced")
        response = use_case.execute(request)

        assert isinstance(response, AssessRiskResponse)
        assert response.ticker == "BBCA"
        assert response.assessment is not None
        assert response.assessment.sensitivity == RiskProfile.BALANCED

    def test_execute_uses_specified_profile(self):
        """Should use the profile specified in request."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        conservative_resp = use_case.execute(
            AssessRiskRequest(ticker="BBCA", sensitivity="conservative")
        )
        aggressive_resp = use_case.execute(AssessRiskRequest(ticker="BBCA", sensitivity="aggressive"))

        assert conservative_resp.sensitivity == "conservative"
        assert aggressive_resp.sensitivity == "aggressive"

    def test_execute_uses_specified_periods(self):
        """Should use indicator periods from request."""
        candles = make_trending_candles("BBCA", 150)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(
            ticker="BBCA",
            sensitivity="balanced",
            sma_period=50,
            ema_period=30,
            rsi_period=7,
        )
        response = use_case.execute(request)

        assert response.sma_period == 50
        assert response.ema_period == 30
        assert response.rsi_period == 7

    def test_execute_raises_error_for_insufficient_data(self):
        """Should raise ValueError when insufficient data."""
        repository = MockRepository([])
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="XXXX", sensitivity="balanced")

        with pytest.raises(ValueError, match="Insufficient data"):
            use_case.execute(request)

    def test_execute_raises_error_for_invalid_profile(self):
        """Should raise ValueError for invalid profile name."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA", sensitivity="invalid")

        with pytest.raises(ValueError, match="Invalid sensitivity"):
            use_case.execute(request)

    def test_execute_normalizes_ticker(self):
        """Should normalize ticker to uppercase."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="bbca", sensitivity="balanced")
        response = use_case.execute(request)

        assert response.ticker == "BBCA"


class TestAssessRiskUseCaseAllProfiles:
    """Test AssessRiskUseCase.execute_all_profiles behavior."""

    def test_execute_all_profiles_returns_three_assessments(self):
        """Should return assessments for all three profiles."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA")
        response = use_case.execute_all_profiles(request)

        assert isinstance(response, AssessAllProfilesResponse)
        assert len(response.assessments) == 3

    def test_execute_all_profiles_contains_all_profile_types(self):
        """Should contain conservative, balanced, and aggressive."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA")
        response = use_case.execute_all_profiles(request)

        profiles = [a.sensitivity for a in response.assessments]
        assert RiskProfile.CONSERVATIVE in profiles
        assert RiskProfile.BALANCED in profiles
        assert RiskProfile.AGGRESSIVE in profiles

    def test_execute_all_profiles_raises_error_for_insufficient_data(self):
        """Should raise ValueError when insufficient data."""
        repository = MockRepository([])
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="XXXX")

        with pytest.raises(ValueError, match="Insufficient data"):
            use_case.execute_all_profiles(request)


class TestAssessRiskResponseDTO:
    """Test AssessRiskResponse DTO properties."""

    def test_response_risk_level_property(self):
        """Should expose risk level as string."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA", sensitivity="balanced")
        response = use_case.execute(request)

        assert response.risk_level in ("open", "BLOCKED")

    def test_response_confidence_property(self):
        """Should expose confidence as int."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA", sensitivity="balanced")
        response = use_case.execute(request)

        assert isinstance(response.confidence, int)
        assert 0 <= response.confidence <= 100

    def test_response_profile_property(self):
        """Should expose profile name as string."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA", sensitivity="conservative")
        response = use_case.execute(request)

        assert response.sensitivity == "conservative"


class TestAssessRiskRequestDTO:
    """Test AssessRiskRequest DTO defaults."""

    def test_default_values(self):
        """Request should have sensible defaults."""
        request = AssessRiskRequest(ticker="BBCA")

        assert request.sensitivity == "balanced"
        assert request.sma_period == 20
        assert request.ema_period == 20
        assert request.rsi_period == 14

    def test_custom_values_override_defaults(self):
        """Custom values should override defaults."""
        request = AssessRiskRequest(
            ticker="BBCA",
            sensitivity="conservative",
            sma_period=50,
            ema_period=30,
            rsi_period=7,
        )

        assert request.sensitivity == "conservative"
        assert request.sma_period == 50
        assert request.ema_period == 30
        assert request.rsi_period == 7


class TestAssessRiskDeterminism:
    """Test that AssessRiskUseCase produces deterministic results."""

    def test_same_input_same_output(self):
        """Same input should always produce same output."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA", sensitivity="balanced")

        response1 = use_case.execute(request)
        response2 = use_case.execute(request)

        assert response1.assessment.gate_triggered == response2.assessment.gate_triggered
        assert response1.assessment.gate_confidence == response2.assessment.gate_confidence
        assert response1.assessment.rationale == response2.assessment.rationale

    def test_different_profiles_may_differ(self):
        """Different profiles may produce different results."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        conservative = use_case.execute(AssessRiskRequest(ticker="BBCA", sensitivity="conservative"))
        aggressive = use_case.execute(AssessRiskRequest(ticker="BBCA", sensitivity="aggressive"))

        # They may be the same or different - the point is they're both valid
        assert conservative.assessment.sensitivity == RiskProfile.CONSERVATIVE
        assert aggressive.assessment.sensitivity == RiskProfile.AGGRESSIVE


class TestAssessRiskIntegration:
    """Integration tests verifying rule application."""

    def test_uses_latest_snapshot(self):
        """Should evaluate the most recent indicator snapshot."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA", sensitivity="balanced")
        response = use_case.execute(request)

        # The snapshot date should be recent (within the data range)
        snapshot_date = response.assessment.snapshot_date
        latest_candle_date = candles[-1].date
        assert snapshot_date <= latest_candle_date

    def test_assessment_contains_indicator_values(self):
        """Assessment should contain the indicator snapshot used."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA", sensitivity="balanced")
        response = use_case.execute(request)

        indicators = response.assessment.indicators
        assert indicators.sma > 0
        assert indicators.ema > 0
        assert 0 <= indicators.rsi <= 100

    def test_assessment_has_rationale(self):
        """Assessment should include rationale explaining the decision."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)
        use_case = AssessRiskUseCase(repository)

        request = AssessRiskRequest(ticker="BBCA", sensitivity="balanced")
        response = use_case.execute(request)

        assert len(response.assessment.rationale) > 0
        rationale_text = " ".join(response.assessment.rationale)
        assert len(rationale_text) > 0
