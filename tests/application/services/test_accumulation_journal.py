"""Unit tests for AccumulationJournalService."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.services.accumulation_journal import AccumulationJournalService
from src.application.use_case.accumulation_screen import AccumulationCandidate
from src.domain.entities.candle import Candle
from src.domain.value_objects.accumulation_journal_entry import AccumulationJournalEntry

# ── helpers ─────────────────────────────────────────────────────────────────

def _make_candidate(
    ticker="BBRI",
    score=75.0,
    streak=6,
    vwap=4.5,
    flow=18.0,
    bb=0.15,
    rsi=42.0,
    trend="SIDE",
) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=ticker,
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=5 / 7,
        total_net_value=Decimal("1000000000"),
        consecutive_streak=streak,
        foreign_vwap=Decimal("5000"),
        current_price=Decimal("4840"),
        vwap_discount_pct=vwap,
        rsi=rsi,
        trend=trend,
        score=score,
        top_brokers=None,
        institutional_flag=False,
        avg_flow_ratio=flow,
        bb_width_pctile=bb,
    )


def _make_entry(
    ticker="BBRI",
    logged_at=date(2026, 5, 1),
    score=75.0,
    streak=6,
    window_days=7,
    pattern="building",
    actual_close_10d: Decimal | None = None,
    actual_close_5d: Decimal | None = None,
    actual_close_20d: Decimal | None = None,
    max_close: Decimal | None = None,
    min_close: Decimal | None = None,
    vwap_disc_pct: Decimal | None = Decimal("4.5"),
    flow_pct: Decimal | None = Decimal("18"),
    bb_pctile: Decimal | None = Decimal("0.15"),
    entry_price: Decimal = Decimal("4840"),
    classification: str | None = None,
) -> AccumulationJournalEntry:
    return AccumulationJournalEntry(
        logged_at=logged_at,
        ticker=ticker,
        entry_price=entry_price,
        window_days=window_days,
        score=score,
        streak=streak,
        flow_pct=flow_pct,
        vwap_disc_pct=vwap_disc_pct,
        bb_pctile=bb_pctile,
        rsi=Decimal("42.0"),
        trend="SIDE",
        pattern=pattern,
        preset="foreign-bounce" if classification else None,
        classification=classification,
        failed_gates=("trend: DOWN (required SIDE)",) if classification == "WATCH" else (),
        regime="SIDEWAYS" if classification else None,
        planned_entry=entry_price if classification else None,
        planned_stop=Decimal("4598") if classification else None,
        planned_target=Decimal("5082") if classification else None,
        max_hold_days=10 if classification else None,
        actual_close_5d=actual_close_5d,
        actual_close_10d=actual_close_10d,
        actual_close_20d=actual_close_20d,
        max_close_in_horizon=max_close,
        min_close_in_horizon=min_close,
    )


def _make_candle(d: date, close: float, ticker="BBRI") -> Candle:
    return Candle(
        ticker=ticker,
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=1000000,
    )


def _make_service(store, repo) -> AccumulationJournalService:
    return AccumulationJournalService(store=store, repository=repo)


# ── TestLogCandidate ─────────────────────────────────────────────────────────

class TestLogCandidate:
    def test_log_with_full_candidate_maps_all_fields(self):
        store = MagicMock()
        store.append.return_value = 1
        service = _make_service(store, MagicMock())
        candidate = _make_candidate()

        count = service.log_candidate(
            ticker="BBRI",
            entry_price=Decimal("4840"),
            window_days=7,
            candidate=candidate,
            logged_at=date(2026, 5, 1),
            pattern="building",
        )

        assert count == 1
        stored_entry: AccumulationJournalEntry = store.append.call_args[0][0][0]
        assert stored_entry.ticker == "BBRI"
        assert stored_entry.score == 75.0
        assert stored_entry.streak == 6
        assert stored_entry.trend == "SIDE"
        assert stored_entry.pattern == "building"
        assert stored_entry.entry_price == Decimal("4840")
        assert stored_entry.window_days == 7

    def test_log_with_none_candidate_writes_zero_score_and_none_signals(self):
        store = MagicMock()
        store.append.return_value = 1
        service = _make_service(store, MagicMock())

        service.log_candidate(
            ticker="BBRI",
            entry_price=Decimal("4840"),
            window_days=7,
            candidate=None,
            logged_at=date(2026, 5, 1),
        )

        entry: AccumulationJournalEntry = store.append.call_args[0][0][0]
        assert entry.score == 0.0
        assert entry.streak == 0
        assert entry.flow_pct is None
        assert entry.vwap_disc_pct is None
        assert entry.bb_pctile is None
        assert entry.rsi is None
        assert entry.trend is None

    def test_log_converts_float_signals_to_decimal_four_decimal_precision(self):
        store = MagicMock()
        store.append.return_value = 1
        service = _make_service(store, MagicMock())
        candidate = _make_candidate(vwap=1.234567)

        service.log_candidate(
            ticker="BBRI",
            entry_price=Decimal("4840"),
            window_days=7,
            candidate=candidate,
            logged_at=date(2026, 5, 1),
        )

        entry: AccumulationJournalEntry = store.append.call_args[0][0][0]
        assert entry.vwap_disc_pct == Decimal("1.2346")

    def test_log_converts_none_float_signals_to_none_decimal(self):
        store = MagicMock()
        store.append.return_value = 1
        service = _make_service(store, MagicMock())
        candidate = _make_candidate(flow=None, bb=None, rsi=None)

        service.log_candidate(
            ticker="BBRI",
            entry_price=Decimal("4840"),
            window_days=7,
            candidate=candidate,
            logged_at=date(2026, 5, 1),
        )

        entry: AccumulationJournalEntry = store.append.call_args[0][0][0]
        assert entry.flow_pct is None
        assert entry.bb_pctile is None
        assert entry.rsi is None

    def test_log_returns_zero_on_duplicate(self):
        store = MagicMock()
        store.append.return_value = 0
        service = _make_service(store, MagicMock())

        result = service.log_candidate(
            ticker="BBRI",
            entry_price=Decimal("4840"),
            window_days=7,
            candidate=_make_candidate(),
            logged_at=date(2026, 5, 1),
        )
        assert result == 0

    def test_log_default_pattern_is_none(self):
        store = MagicMock()
        store.append.return_value = 1
        service = _make_service(store, MagicMock())

        service.log_candidate(
            ticker="BBRI",
            entry_price=Decimal("4840"),
            window_days=7,
            candidate=_make_candidate(),
            logged_at=date(2026, 5, 1),
        )

        entry: AccumulationJournalEntry = store.append.call_args[0][0][0]
        assert entry.pattern is None

    def test_log_from_analysis_fields_are_mapped(self):
        store = MagicMock()
        store.append.return_value = 1
        service = _make_service(store, MagicMock())

        service.log_candidate(
            ticker="BBRI",
            entry_price=Decimal("4840"),
            window_days=7,
            candidate=_make_candidate(),
            logged_at=date(2026, 5, 1),
            preset="foreign-bounce",
            classification="WATCH",
            failed_gates=("trend: DOWN (required SIDE)",),
            regime="SIDEWAYS",
            planned_entry=Decimal("4840"),
            planned_stop=Decimal("4598"),
            planned_target=Decimal("5082"),
            max_hold_days=10,
        )

        entry: AccumulationJournalEntry = store.append.call_args[0][0][0]
        assert entry.preset == "foreign-bounce"
        assert entry.classification == "WATCH"
        assert entry.failed_gates == ("trend: DOWN (required SIDE)",)
        assert entry.regime == "SIDEWAYS"
        assert entry.planned_entry == Decimal("4840")
        assert entry.planned_stop == Decimal("4598")
        assert entry.planned_target == Decimal("5082")
        assert entry.max_hold_days == 10


# ── TestReviewEmptyAndShortCircuit ───────────────────────────────────────────

class TestReviewEmptyAndShortCircuit:
    def test_review_returns_zeroed_report_when_store_is_empty(self):
        store = MagicMock()
        store.read_all.return_value = []
        repo = MagicMock()
        service = _make_service(store, repo)

        report = service.review()

        assert report.total_entries == 0
        assert report.enriched_entries == 0
        assert report.score_buckets == []
        repo.get_candles.assert_not_called()

    def test_review_skips_enrichment_for_already_enriched_entries(self):
        entry = _make_entry(actual_close_10d=Decimal("5000"))
        store = MagicMock()
        store.read_all.return_value = [entry]
        repo = MagicMock()
        service = _make_service(store, repo)

        service.review()

        repo.get_candles.assert_not_called()
        store.update_review_fields.assert_not_called()

    def test_review_groups_enriched_entries_by_preset_decision(self):
        entries = [
            _make_entry(
                ticker="AAA",
                classification="ENTER",
                actual_close_10d=Decimal("5324"),
                max_close=Decimal("5400"),
                min_close=Decimal("4800"),
            ),
            _make_entry(
                ticker="BBB",
                classification="WATCH",
                actual_close_10d=Decimal("4598"),
                max_close=Decimal("4900"),
                min_close=Decimal("4500"),
            ),
        ]
        store = MagicMock()
        store.read_all.return_value = entries
        service = _make_service(store, MagicMock())

        report = service.review()

        by_decision = {stat.decision: stat for stat in report.by_decision}
        assert by_decision["ENTER"].avg_return_10d == 10.0
        assert by_decision["ENTER"].win_rate_10d == 100.0
        assert by_decision["WATCH"].avg_return_10d == -5.0
        assert by_decision["WATCH"].win_rate_10d == 0.0

    def test_review_does_not_call_update_when_no_new_enrichment(self):
        """All entries lack data but candles are also unavailable."""
        entry = _make_entry(actual_close_10d=None)
        store = MagicMock()
        store.read_all.side_effect = [[entry], [entry]]
        repo = MagicMock()
        repo.get_candles.return_value = []
        service = _make_service(store, repo)

        service.review()

        store.update_review_fields.assert_not_called()


# ── TestReviewEnrichment ─────────────────────────────────────────────────────

class TestReviewEnrichment:
    def _make_forward_candles(
        self, start_date: date, count: int, start_price: float = 5000.0
    ) -> list[Candle]:
        """Generate count candles starting from start_date + 1 day."""
        from datetime import timedelta
        candles = []
        d = start_date
        for i in range(count):
            d = d + timedelta(days=1)
            # skip weekends for realism
            while d.weekday() >= 5:
                d = d + timedelta(days=1)
            candles.append(_make_candle(d, start_price + i * 10))
        return candles

    def test_review_enriches_5th_10th_and_20th_candle_close(self):
        logged_at = date(2026, 4, 1)
        entry = _make_entry(logged_at=logged_at, actual_close_10d=None)
        candles = self._make_forward_candles(logged_at, 25)

        store = MagicMock()
        enriched_entry = None

        def capture_update(entries):
            nonlocal enriched_entry
            enriched_entry = entries[0]

        store.read_all.side_effect = [
            [entry],
            [_make_entry(
                logged_at=logged_at,
                actual_close_10d=candles[9].close,
                actual_close_5d=candles[4].close,
                actual_close_20d=candles[19].close,
            )],
        ]
        store.update_review_fields.side_effect = capture_update

        repo = MagicMock()
        repo.get_candles.return_value = candles
        service = _make_service(store, repo)

        service.review(horizon_days=10)

        store.update_review_fields.assert_called_once()
        args = store.update_review_fields.call_args[0][0]
        assert args[0].actual_close_5d == candles[4].close
        assert args[0].actual_close_10d == candles[9].close
        assert args[0].actual_close_20d == candles[19].close

    def test_review_leaves_entry_unenriched_when_fewer_than_10_candles(self):
        logged_at = date(2026, 4, 1)
        entry = _make_entry(logged_at=logged_at, actual_close_10d=None)
        candles = self._make_forward_candles(logged_at, 7)  # only 7

        store = MagicMock()
        store.read_all.side_effect = [[entry], [entry]]
        repo = MagicMock()
        repo.get_candles.return_value = candles
        service = _make_service(store, repo)

        service.review(horizon_days=10)

        store.update_review_fields.assert_not_called()

    def test_review_filters_candles_strictly_after_logged_at_date(self):
        """A candle on exactly logged_at must not be counted as forward data."""
        logged_at = date(2026, 4, 1)
        entry = _make_entry(logged_at=logged_at, actual_close_10d=None)

        # 1 same-day candle + 10 forward candles
        same_day = _make_candle(logged_at, 4800.0)
        forward = self._make_forward_candles(logged_at, 10, start_price=5000.0)
        candles = [same_day] + forward

        store = MagicMock()
        store.read_all.side_effect = [
            [entry],
            [_make_entry(logged_at=logged_at, actual_close_10d=forward[9].close)],
        ]
        repo = MagicMock()
        repo.get_candles.return_value = candles
        service = _make_service(store, repo)

        service.review(horizon_days=10)

        args = store.update_review_fields.call_args[0][0]
        # 10th candle should be the 10th forward, not 10th from same_day
        assert args[0].actual_close_10d == forward[9].close

    def test_review_max_and_min_computed_over_horizon_window(self):
        logged_at = date(2026, 4, 1)
        entry = _make_entry(logged_at=logged_at, actual_close_10d=None)

        from datetime import timedelta
        # 15 candles with known prices
        candles = []
        d = logged_at
        prices = [5000, 5100, 4900, 5200, 4800, 5300, 4700, 5400, 4600, 5500, 5600, 5700, 5800, 5900, 6000]
        for price in prices:
            d = d + timedelta(days=1)
            candles.append(_make_candle(d, float(price)))

        store = MagicMock()
        store.read_all.side_effect = [[entry], [_make_entry(
            logged_at=logged_at,
            actual_close_10d=candles[9].close,
        )]]
        repo = MagicMock()
        repo.get_candles.return_value = candles
        service = _make_service(store, repo)

        service.review(horizon_days=10)

        args = store.update_review_fields.call_args[0][0]
        # Over first 10 candles: max=5500, min=4600
        assert args[0].max_close_in_horizon == Decimal("5500")
        assert args[0].min_close_in_horizon == Decimal("4600")


# ── TestReviewScoreBuckets ───────────────────────────────────────────────────

class TestReviewScoreBuckets:
    def _service_with_enriched_entries(self, entries):
        store = MagicMock()
        store.read_all.return_value = entries
        repo = MagicMock()
        repo.get_candles.return_value = []  # no new enrichment needed
        return _make_service(store, repo)

    def test_score_buckets_partition_at_70_and_40(self):
        entries = [
            _make_entry(score=30.0, actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")),
            _make_entry(score=40.0, actual_close_10d=Decimal("5000"), entry_price=Decimal("4840"), ticker="A"),
            _make_entry(score=69.9, actual_close_10d=Decimal("5000"), entry_price=Decimal("4840"), ticker="B"),
            _make_entry(score=70.0, actual_close_10d=Decimal("5000"), entry_price=Decimal("4840"), ticker="C"),
            _make_entry(score=90.0, actual_close_10d=Decimal("5000"), entry_price=Decimal("4840"), ticker="D"),
        ]
        service = self._service_with_enriched_entries(entries)

        report = service.review()

        by_bucket = {s.bucket: s for s in report.score_buckets}
        assert by_bucket["70+"].n == 2      # 70.0 and 90.0
        assert by_bucket["40–69"].n == 2  # 40.0 and 69.9
        assert by_bucket["0–39"].n == 1   # 30.0

    def test_score_bucket_win_rate_uses_strict_positive_return(self):
        """A return of exactly 0% counts as a loss."""
        entries = [
            _make_entry(score=80.0, actual_close_10d=Decimal("4840"), entry_price=Decimal("4840"), ticker="A"),  # 0% return
            _make_entry(score=80.0, actual_close_10d=Decimal("5000"), entry_price=Decimal("4840"), ticker="B"),  # positive
        ]
        service = self._service_with_enriched_entries(entries)

        report = service.review()

        by_bucket = {s.bucket: s for s in report.score_buckets}
        # 1 winner out of 2 → 50%
        assert by_bucket["70+"].win_rate_10d == 50.0

    def test_score_bucket_with_no_entries_returns_none_for_metrics(self):
        entries = [
            _make_entry(score=80.0, actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")),
        ]
        service = self._service_with_enriched_entries(entries)

        report = service.review()

        by_bucket = {s.bucket: s for s in report.score_buckets}
        assert by_bucket["0–39"].n == 0
        assert by_bucket["0–39"].avg_return_10d is None
        assert by_bucket["0–39"].win_rate_10d is None


# ── TestReviewPatternStats ───────────────────────────────────────────────────

class TestReviewPatternStats:
    def _service_with_entries(self, entries):
        store = MagicMock()
        store.read_all.return_value = entries
        repo = MagicMock()
        repo.get_candles.return_value = []
        return _make_service(store, repo)

    def test_pattern_none_grouped_as_unknown(self):
        entry = _make_entry(
            pattern=None,
            actual_close_10d=Decimal("5000"),
            entry_price=Decimal("4840"),
        )
        service = self._service_with_entries([entry])

        report = service.review()

        patterns = {s.pattern for s in report.by_pattern}
        assert "unknown" in patterns

    def test_pattern_stats_sorted_by_descending_count(self):
        entries = (
            [_make_entry(pattern="sustained", ticker=f"A{i}", actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")) for i in range(3)]
            + [_make_entry(pattern="weak", ticker=f"B{i}", actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")) for i in range(1)]
            + [_make_entry(pattern="building", ticker=f"C{i}", actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")) for i in range(2)]
        )
        service = self._service_with_entries(entries)

        report = service.review()

        names = [s.pattern for s in report.by_pattern]
        assert names == ["sustained", "building", "weak"]


# ── TestReviewSignalDeltas ───────────────────────────────────────────────────

class TestReviewSignalDeltas:
    def _service_with_entries(self, entries):
        store = MagicMock()
        store.read_all.return_value = entries
        repo = MagicMock()
        repo.get_candles.return_value = []
        return _make_service(store, repo)

    def test_signal_delta_streak_splits_at_five_inclusive(self):
        entries = [
            _make_entry(ticker="A", streak=5, actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")),
            _make_entry(ticker="B", streak=4, actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")),
        ]
        service = self._service_with_entries(entries)

        report = service.review()

        delta = next(d for d in report.signal_deltas if d.signal == "streak")
        assert delta.group_a_n == 1   # streak=5 → group_a
        assert delta.group_b_n == 1   # streak=4 → group_b

    def test_signal_delta_none_vwap_bb_flow_fall_in_group_b(self):
        entries = [
            _make_entry(
                ticker="A",
                vwap_disc_pct=None,
                bb_pctile=None,
                flow_pct=None,
                actual_close_10d=Decimal("5000"),
                entry_price=Decimal("4840"),
            )
        ]
        service = self._service_with_entries(entries)

        report = service.review()

        for d in report.signal_deltas:
            if d.signal in ("vwap_disc", "bb_pctile", "flow_pct"):
                assert d.group_a_n == 0
                assert d.group_b_n == 1

    def test_signal_delta_bb_pctile_threshold_at_0_20_decimal(self):
        entries = [
            _make_entry(ticker="A", bb_pctile=Decimal("0.20"), actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")),  # squeeze
            _make_entry(ticker="B", bb_pctile=Decimal("0.21"), actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")),  # not
        ]
        service = self._service_with_entries(entries)

        report = service.review()

        delta = next(d for d in report.signal_deltas if d.signal == "bb_pctile")
        assert delta.group_a_n == 1  # 0.20 is in squeeze group
        assert delta.group_b_n == 1  # 0.21 is not

    def test_signal_delta_avg_10d_none_when_group_has_no_return_data(self):
        entries = [
            _make_entry(ticker="A", streak=10, actual_close_10d=None, entry_price=Decimal("4840")),
        ]
        # Entry has no actual_close_10d → won't appear in stats at all
        # After re-read, return the same entry (not enriched)
        store = MagicMock()
        store.read_all.side_effect = [[entries[0]], [entries[0]]]
        repo = MagicMock()
        repo.get_candles.return_value = []
        service = _make_service(store, repo)

        report = service.review()

        # enriched_entries = 0 so signal_deltas uses empty with_data list
        for d in report.signal_deltas:
            assert d.group_a_avg_10d is None
            assert d.group_b_avg_10d is None


# ── TestReviewReportTotals ───────────────────────────────────────────────────

class TestReviewReportTotals:
    def test_total_entries_and_enriched_counts_correctly(self):
        entries = [
            _make_entry(ticker="A", actual_close_10d=Decimal("5000"), entry_price=Decimal("4840")),
            _make_entry(ticker="B", actual_close_10d=Decimal("5100"), entry_price=Decimal("4840")),
            _make_entry(ticker="C", actual_close_10d=None),
        ]
        store = MagicMock()
        store.read_all.side_effect = [entries, entries]
        repo = MagicMock()
        repo.get_candles.return_value = []  # can't enrich C
        service = _make_service(store, repo)

        report = service.review()

        assert report.total_entries == 3
        assert report.enriched_entries == 2
