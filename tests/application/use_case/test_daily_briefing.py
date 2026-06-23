"""Tests for DailyBriefingUseCase."""

from datetime import date
from unittest.mock import MagicMock, patch

from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingRequest,
    DailyBriefingUseCase,
)


def test_daily_briefing_rolls_back_weekends():
    market_repo = MagicMock()
    market_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    regime_uc.execute.return_value = None

    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
    )

    # Mocking date.today() via patch of daily_briefing's imported date class
    with patch("src.application.use_case.daily_briefing_use_case.date") as mock_date:
        # Saturday, June 20, 2026
        mock_date.today.return_value = date(2026, 6, 20)
        # Ensure side_effect allows creating new date instances in the code
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        response = use_case.execute(DailyBriefingRequest(as_of_date=None))
        # Should roll back Saturday to Friday, June 19, 2026
        assert response.as_of_date == date(2026, 6, 19)

        # Sunday, June 21, 2026
        mock_date.today.return_value = date(2026, 6, 21)
        response = use_case.execute(DailyBriefingRequest(as_of_date=None))
        # Should roll back Sunday to Friday, June 19, 2026
        assert response.as_of_date == date(2026, 6, 19)
