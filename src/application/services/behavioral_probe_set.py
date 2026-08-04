"""Frozen behavioural probe set for ACCUMULATION_DISCOVERY cohort identity.

Layer: Application

ADR-068 replaces proxy-based cohort identity (config bytes, hand-typed engine
version constants) with a direct measurement: a frozen set of synthetic
candidates is driven through the production accum decision path and the
canonical output projection is hashed.

This module owns the **inputs** only — pure frozen data plus deterministic
builders that expand them into domain entities. It performs no IO, reads no
clock, and imports nothing outside domain value objects/entities. Execution
lives in ``behavioral_probe_runner``.

Two probe sets exist (ADR-068 §3):

- **core**: identity material. Adding or changing a core probe is a deliberate
  cohort boundary.
- **extended**: coverage/mutation material only. Never enters identity.

Extended probes are deliberately *not* identity material: a mutation that only
an extended probe reaches is measured and named, but it does not fork the
cohort. Adding one to core is a separate, deliberate cohort boundary.

History of the core set: slice 1 shipped 15 core probes with an empty extended
set; slice 2 added 4 extended probes (swing setup catalog) without touching
identity; four further **core** probes were then added to close named surviving
mutants recorded by the slice-2 mutation suite. That last step deliberately
moved both frozen digests — see ADR-068 §3 and the record in
``tests/application/services/test_behavioral_probe_coverage_and_mutation.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.domain.value_objects.shareholding_composition import ShareholdingComposition

# Identity of the frozen core set. Bumping this is a cohort boundary.
CORE_PROBE_SET_ID = "accum_core.v1"
EXTENDED_PROBE_SET_ID = "accum_extended.v1"

# Every probe supplies its own economic date. Nothing in this package may read
# a clock — see ADR-068 §4.
PROBE_AS_OF_DATE = date(2026, 6, 19)

# Members of TIER1_FOREIGN_BROKERS, so BCI CLUSTER/STABLE is reachable.
_TIER1_CODES = ("AK", "BK", "ZP")
# Deliberately outside the tier-1 set, so BCI RETAIL-LED is reachable.
_RETAIL_CODES = ("YP", "PD", "CC")


@dataclass(frozen=True)
class ProbeFundamentals:
    """Frozen fundamentals stub input for one probe ticker."""

    piotroski_f_score: int | None
    market_cap_idr: int | None
    pe_ratio_ttm: float | None = 12.0
    roe_ttm: float | None = 14.0
    net_profit_margin: float | None = 9.0
    revenue_yoy_growth: float | None = 6.0
    dividend_yield: float | None = 2.0
    week52_high: float | None = 1500.0
    week52_low: float | None = 900.0
    near_52w_high_rank: float | None = 45.0

    def to_value_object(self, ticker: str) -> CompanyFundamentals:
        return CompanyFundamentals(
            ticker=ticker,
            pe_ratio_ttm=self.pe_ratio_ttm,
            roe_ttm=self.roe_ttm,
            net_profit_margin=self.net_profit_margin,
            revenue_yoy_growth=self.revenue_yoy_growth,
            piotroski_f_score=self.piotroski_f_score,
            dividend_yield=self.dividend_yield,
            week52_high=self.week52_high,
            week52_low=self.week52_low,
            near_52w_high_rank=self.near_52w_high_rank,
            market_cap_idr=self.market_cap_idr,
        )


@dataclass(frozen=True)
class ProbeShareholding:
    """Frozen shareholding stub input for one probe ticker."""

    institution_pct: float
    individual_pct: float
    top_holder_pct: float
    report_date: date = date(2026, 3, 31)
    top_holder_name: str = "PROBE HOLDINGS"

    def to_value_object(self, ticker: str) -> ShareholdingComposition:
        return ShareholdingComposition(
            ticker=ticker,
            report_date=self.report_date,
            institution_pct=self.institution_pct,
            individual_pct=self.individual_pct,
            top_holder_name=self.top_holder_name,
            top_holder_pct=self.top_holder_pct,
        )


@dataclass(frozen=True)
class ProbeBandar:
    """Frozen bandar-detector stub input for one probe ticker."""

    five_day_accdist: str
    today_accdist: str = "Small Accum"
    broker_accdist: str = "Big Accum"
    top1_accdist: str = "Big Accum"
    top1_percent: float = 11.0
    today_percent: float = 4.0
    total_buyer: int = 22
    total_seller: int = 17

    def to_value_object(self, ticker: str, session_date: date) -> BandarDetectorSnapshot:
        return BandarDetectorSnapshot(
            ticker=ticker,
            session_date=session_date,
            broker_accdist=self.broker_accdist,
            today_accdist=self.today_accdist,
            five_day_accdist=self.five_day_accdist,
            top1_accdist=self.top1_accdist,
            top1_percent=self.top1_percent,
            today_percent=self.today_percent,
            total_buyer=self.total_buyer,
            total_seller=self.total_seller,
        )


@dataclass(frozen=True)
class ProbeForwardEstimates:
    """Frozen forward-estimate stub input for one probe ticker.

    Only the fields the accum decision path can read are modelled.
    ``forward_eps_1y`` combined with the probe's own closing price is what
    ``SignalContext.forward_pe`` is derived from, which is the single input
    the ``valuation_stretched`` signal flag compares.
    """

    forward_eps_1y: float
    revenue_forward_1y: float | None = None

    def to_value_object(self, ticker: str) -> ForwardEstimates:
        return ForwardEstimates(
            ticker=ticker,
            forward_eps_1y=self.forward_eps_1y,
            revenue_forward_1y=self.revenue_forward_1y,
            # Left unset so the production enricher derives forward_pe from the
            # probe's own frozen close price rather than a second stated price.
            current_price=None,
            forward_pe=None,
            fetched_at=None,
        )


@dataclass(frozen=True)
class ProbeCandleTail:
    """Frozen deterministic override for the final sessions of a price series.

    The two-segment ``price_step`` / ``pullback_step`` builder can only draw
    monotone runs, which pins RSI at 100, pins Bollinger band-width percentile
    at 1.0, and makes every session's volume identical. Three regions of the
    accum decision surface are unreachable under those constraints: the RSI
    branch of EXHAUSTION, the band-width branch of COMPRESSION, and the
    dry-up/expansion volume trigger.

    A tail states the last ``sessions`` closes as a cycled delta pattern plus a
    cycled volume pattern, so a probe can place RSI, band-width percentile, and
    volume shape deliberately. Everything here is frozen literal data expanded
    by pure arithmetic — no clock, file, or provider is involved.

    ``body`` is ``close - open``: a positive body makes every tail session a
    bullish candle, which is what the volume-trigger expansion rule and the
    breakout price gate both read.
    """

    sessions: int
    close_deltas: tuple[str, ...]
    volumes: tuple[int, ...] = ()
    body: str = "0"
    wick: str = "2"


@dataclass(frozen=True)
class ProbeTicker:
    """One frozen synthetic ticker: price series, foreign flow, enrichment.

    ``net_buy_pattern`` is read oldest-session-first and cycled to cover
    ``broker_sessions``. ``True`` means the session is foreign-accumulating.
    """

    ticker: str
    candle_sessions: int
    base_price: int
    price_step: str
    daily_volume: int
    broker_sessions: int
    net_buy_pattern: tuple[bool, ...]
    accumulating_buy_value_idr: int
    accumulating_sell_value_idr: int
    distributing_buy_value_idr: int
    distributing_sell_value_idr: int
    foreign_buy_lot: int
    foreign_sell_lot: int
    session_turnover_idr: int
    tier1_net_buyers: int
    retail_net_buyers: int
    tier1_net_lot: int
    retail_net_lot: int
    fundamentals: ProbeFundamentals | None = None
    shareholding: ProbeShareholding | None = None
    bandar: ProbeBandar | None = None
    forward_estimates: ProbeForwardEstimates | None = None
    # Trailing price drift applied to the last ``pullback_sessions`` candles.
    # Lets a probe place RSI in a chosen band without abandoning the primary
    # trend, so the RSI-headroom scoring branch is reachable.
    pullback_sessions: int = 0
    pullback_step: str = "0"
    # Optional explicit override of the final sessions. Applied last, so it
    # wins over both the primary step and the pullback drift.
    tail: ProbeCandleTail | None = None


@dataclass(frozen=True)
class BehavioralProbe:
    """One frozen screen run: request knobs plus its synthetic universe.

    A probe is a whole screen execution rather than a single candidate so the
    canonical projection can carry ordering and inclusion/exclusion, which
    ADR-068 §2 names as part of the behavioural output.
    """

    probe_id: str
    surface: str
    tickers: tuple[ProbeTicker, ...]
    as_of_date: date = PROBE_AS_OF_DATE
    window_days: int = 7
    min_net_buy_days: int = 2
    min_accum_score: float = 0.0
    min_accum_score_enabled: bool = True
    min_signal_score: float = 0.0
    min_signal_score_enabled: bool = False
    min_market_cap_idr: int = 0
    min_piotroski: int = 0
    resistance_gate_enabled: bool = True
    resistance_headroom_min_pct: float = 5.0
    # None means "no MarketContext supplied" — DecisionPolicy's own default
    # regime path, which is itself a branch worth measuring.
    regime: str | None = None
    regime_conviction: float = 0.7
    regime_signal_multiplier: float = 1.0
    regime_gate_tightening: bool = False
    # When False, no fundamentals/shareholding/bandar stub is wired at all, so
    # the missing-evidence branches of the real gates are exercised.
    enrichment_providers_enabled: bool = True
    # When True, the real AssessSourceAvailabilityUseCase runs over a frozen
    # in-memory session calendar, so evidence authority coverage resolves and
    # the ENTER branch is reachable. When False, availability is unresolved —
    # the zero-coverage branch production also has.
    source_availability_enabled: bool = True
    # When True the runner attaches its frozen swing setup catalog, so a
    # primary setup family resolves and the setup-readiness evaluator, the
    # setup-family branches of DecisionPolicy, and the named-setup gate
    # evaluator all become reachable. Production attaches a catalog built from
    # `config/swing_setups.yaml`; no core probe sets this flag, so enabling it
    # on an extended probe cannot move cohort identity (ADR-068 §3).
    swing_setup_families_enabled: bool = False
    rsi_period: int | None = None
    sma_period: int | None = None
    extra_notes: tuple[str, ...] = field(default_factory=tuple)


def probe_sessions(*, end_date: date, count: int) -> tuple[date, ...]:
    """Return ``count`` weekday sessions ending on ``end_date``, oldest first.

    Pure calendar arithmetic on a supplied date — never a real exchange
    calendar lookup and never a clock read.
    """
    if count <= 0:
        return ()
    days: list[date] = []
    cursor = end_date
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return tuple(reversed(days))


def _base_close(spec: ProbeTicker, index: int, *, session_count: int) -> Decimal:
    step = Decimal(spec.price_step)
    base = Decimal(spec.base_price)
    pullback_start = session_count - max(spec.pullback_sessions, 0)
    if spec.pullback_sessions > 0 and index >= pullback_start:
        peak = base + step * (pullback_start - 1)
        close = peak + Decimal(spec.pullback_step) * (index - pullback_start + 1)
    else:
        close = base + step * index
    return close if close > Decimal("0") else Decimal("1")


def _tail_closes_and_volumes(
    spec: ProbeTicker, *, session_count: int
) -> tuple[dict[int, Decimal], dict[int, int]]:
    """Expand a frozen tail into ``{index -> close}`` and ``{index -> volume}``.

    Deltas and volumes are cycled oldest-first over the tail, anchored on the
    close the base series would have produced immediately before the tail.
    """
    tail = spec.tail
    if tail is None or tail.sessions <= 0 or not tail.close_deltas:
        return {}, {}
    start = max(session_count - tail.sessions, 0)
    anchor = (
        _base_close(spec, start - 1, session_count=session_count)
        if start > 0
        else Decimal(spec.base_price)
    )
    closes: dict[int, Decimal] = {}
    volumes: dict[int, int] = {}
    close = anchor
    for offset, index in enumerate(range(start, session_count)):
        close = close + Decimal(tail.close_deltas[offset % len(tail.close_deltas)])
        if close <= Decimal("0"):
            close = Decimal("1")
        closes[index] = close
        if tail.volumes:
            volumes[index] = tail.volumes[offset % len(tail.volumes)]
    return closes, volumes


def build_probe_candles(spec: ProbeTicker, *, as_of_date: date) -> tuple[Candle, ...]:
    """Expand a ticker spec into its frozen OHLCV series."""
    sessions = probe_sessions(end_date=as_of_date, count=spec.candle_sessions)
    session_count = len(sessions)
    tail_closes, tail_volumes = _tail_closes_and_volumes(spec, session_count=session_count)
    body = Decimal(spec.tail.body) if spec.tail is not None else Decimal("0")
    wick = Decimal(spec.tail.wick) if spec.tail is not None else Decimal("2")
    candles: list[Candle] = []
    for index, session in enumerate(sessions):
        if index in tail_closes:
            close = tail_closes[index]
            open_price = close - body
            if open_price <= Decimal("0"):
                open_price = Decimal("1")
            high = max(close, open_price) + wick
            low = min(close, open_price) - wick
            volume = tail_volumes.get(index, spec.daily_volume)
        else:
            close = _base_close(spec, index, session_count=session_count)
            open_price = close
            high = close + Decimal("2")
            low = close - Decimal("2")
            volume = spec.daily_volume
        candles.append(
            Candle(
                ticker=spec.ticker,
                date=session,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return tuple(candles)


def build_probe_broker_summaries(
    spec: ProbeTicker, *, as_of_date: date
) -> tuple[BrokerSummary, ...]:
    """Expand a ticker spec into its frozen foreign-flow summary series."""
    sessions = probe_sessions(end_date=as_of_date, count=spec.broker_sessions)
    pattern = spec.net_buy_pattern or (True,)
    summaries: list[BrokerSummary] = []
    for index, session in enumerate(sessions):
        accumulating = pattern[index % len(pattern)]
        buy_value = Decimal(
            spec.accumulating_buy_value_idr if accumulating else spec.distributing_buy_value_idr
        )
        sell_value = Decimal(
            spec.accumulating_sell_value_idr if accumulating else spec.distributing_sell_value_idr
        )
        summaries.append(
            BrokerSummary(
                ticker=spec.ticker,
                date=session,
                top_buyers=(),
                top_sellers=(),
                foreign_buy_value=buy_value,
                foreign_sell_value=sell_value,
                foreign_buy_lot=spec.foreign_buy_lot,
                foreign_sell_lot=spec.foreign_sell_lot,
                total_value=Decimal(spec.session_turnover_idr),
                total_lot=spec.foreign_buy_lot + spec.foreign_sell_lot + 1_000,
            )
        )
    return tuple(summaries)


def build_probe_daily_flows(spec: ProbeTicker, *, as_of_date: date) -> tuple[BrokerDailyFlow, ...]:
    """Expand a ticker spec into its frozen per-broker daily flow rows.

    ``tier1_net_buyers`` drives the BCI label the real evaluator derives
    (CLUSTER / STABLE / RETAIL-LED), so probes can cover all three.
    """
    sessions = probe_sessions(end_date=as_of_date, count=spec.broker_sessions)
    rows: list[BrokerDailyFlow] = []
    members: list[tuple[str, int]] = [
        (code, spec.tier1_net_lot) for code in _TIER1_CODES[: spec.tier1_net_buyers]
    ]
    members += [(code, spec.retail_net_lot) for code in _RETAIL_CODES[: spec.retail_net_buyers]]
    for session in sessions:
        for code, net_lot in members:
            net_value = Decimal(net_lot * 100 * 1_000)
            rows.append(
                BrokerDailyFlow(
                    ticker=spec.ticker,
                    broker_code=code,
                    broker_name=code,
                    date=session,
                    buy_lot=max(net_lot, 0),
                    sell_lot=max(-net_lot, 0),
                    net_lot=net_lot,
                    buy_value=net_value if net_value > 0 else Decimal("0"),
                    sell_value=-net_value if net_value < 0 else Decimal("0"),
                    net_value=net_value,
                    avg_buy_price=Decimal("1000"),
                    avg_sell_price=Decimal("1000"),
                    avg_price=Decimal("1000"),
                    buy_pct=0.0,
                    sell_pct=0.0,
                )
            )
    return tuple(rows)


# ── Frozen ticker archetypes ────────────────────────────────────────────────
# Each archetype targets a distinct region of the accum decision surface.
# Values are frozen: changing one is a deliberate cohort boundary.

_STRONG_ACCUM = ProbeTicker(
    ticker="PRBA",
    candle_sessions=260,
    base_price=1_000,
    price_step="1.5",
    daily_volume=9_000_000,
    broker_sessions=10,
    net_buy_pattern=(True,),
    accumulating_buy_value_idr=14_000_000_000,
    accumulating_sell_value_idr=1_000_000_000,
    distributing_buy_value_idr=1_000_000_000,
    distributing_sell_value_idr=8_000_000_000,
    foreign_buy_lot=90_000,
    foreign_sell_lot=6_000,
    session_turnover_idr=18_000_000_000,
    pullback_sessions=8,
    pullback_step="-4",
    tier1_net_buyers=3,
    retail_net_buyers=1,
    tier1_net_lot=900,
    retail_net_lot=-400,
    fundamentals=ProbeFundamentals(piotroski_f_score=8, market_cap_idr=62_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=58.0, individual_pct=42.0, top_holder_pct=52.0),
    bandar=ProbeBandar(five_day_accdist="Big Accum"),
)

_MODERATE_ACCUM = ProbeTicker(
    ticker="PRBB",
    candle_sessions=260,
    base_price=1_800,
    price_step="0.4",
    daily_volume=6_000_000,
    broker_sessions=10,
    net_buy_pattern=(True, True, False, True, False),
    accumulating_buy_value_idr=7_000_000_000,
    accumulating_sell_value_idr=2_500_000_000,
    distributing_buy_value_idr=2_000_000_000,
    distributing_sell_value_idr=5_000_000_000,
    foreign_buy_lot=45_000,
    foreign_sell_lot=20_000,
    session_turnover_idr=28_000_000_000,
    tier1_net_buyers=1,
    retail_net_buyers=2,
    tier1_net_lot=500,
    retail_net_lot=300,
    # Trailing drift chosen so the real detector reports phase NONE.
    pullback_sessions=10,
    pullback_step="-5",
    fundamentals=ProbeFundamentals(piotroski_f_score=6, market_cap_idr=21_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=44.0, individual_pct=56.0, top_holder_pct=48.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
)

_WEAK_FLOW = ProbeTicker(
    ticker="PRBC",
    candle_sessions=260,
    base_price=2_600,
    price_step="-0.8",
    daily_volume=4_000_000,
    broker_sessions=10,
    net_buy_pattern=(False, False, True, False, False),
    accumulating_buy_value_idr=3_000_000_000,
    accumulating_sell_value_idr=2_800_000_000,
    distributing_buy_value_idr=1_200_000_000,
    distributing_sell_value_idr=6_500_000_000,
    foreign_buy_lot=12_000,
    foreign_sell_lot=48_000,
    session_turnover_idr=18_000_000_000,
    tier1_net_buyers=0,
    retail_net_buyers=3,
    tier1_net_lot=0,
    retail_net_lot=250,
    # Trailing drift chosen so the real trend classifier reports DOWN.
    pullback_sessions=20,
    pullback_step="-6",
    fundamentals=ProbeFundamentals(piotroski_f_score=5, market_cap_idr=9_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=31.0, individual_pct=69.0, top_holder_pct=40.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
)

_BANDAR_DISTRIBUTING = ProbeTicker(
    ticker="PRBD",
    candle_sessions=260,
    base_price=1_400,
    price_step="0.9",
    daily_volume=7_000_000,
    broker_sessions=10,
    net_buy_pattern=(True, True, True, False),
    accumulating_buy_value_idr=9_000_000_000,
    accumulating_sell_value_idr=2_000_000_000,
    distributing_buy_value_idr=1_500_000_000,
    distributing_sell_value_idr=7_000_000_000,
    foreign_buy_lot=52_000,
    foreign_sell_lot=15_000,
    session_turnover_idr=30_000_000_000,
    tier1_net_buyers=2,
    retail_net_buyers=1,
    tier1_net_lot=700,
    retail_net_lot=-200,
    # Trailing drift chosen so the real detector reports phase ACCUMULATION.
    pullback_sessions=8,
    pullback_step="-4",
    fundamentals=ProbeFundamentals(piotroski_f_score=7, market_cap_idr=33_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=51.0, individual_pct=49.0, top_holder_pct=46.0),
    # Matches the frozen BandarGate distribution label set.
    bandar=ProbeBandar(five_day_accdist="Big Dist"),
)

_DISTRESSED_FUNDAMENTALS = ProbeTicker(
    ticker="PRBE",
    candle_sessions=260,
    base_price=900,
    price_step="0.6",
    daily_volume=8_000_000,
    broker_sessions=10,
    net_buy_pattern=(True, True, False),
    accumulating_buy_value_idr=8_500_000_000,
    accumulating_sell_value_idr=1_800_000_000,
    distributing_buy_value_idr=1_400_000_000,
    distributing_sell_value_idr=6_000_000_000,
    foreign_buy_lot=48_000,
    foreign_sell_lot=14_000,
    session_turnover_idr=26_000_000_000,
    tier1_net_buyers=2,
    retail_net_buyers=2,
    tier1_net_lot=600,
    retail_net_lot=150,
    # Below the frozen FundamentalGate distress threshold.
    fundamentals=ProbeFundamentals(piotroski_f_score=1, market_cap_idr=27_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=39.0, individual_pct=61.0, top_holder_pct=44.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
)

_THIRD_LINER = ProbeTicker(
    ticker="PRBF",
    candle_sessions=260,
    base_price=190,
    price_step="0.2",
    daily_volume=300_000,
    broker_sessions=10,
    net_buy_pattern=(True, False, True),
    accumulating_buy_value_idr=900_000_000,
    accumulating_sell_value_idr=200_000_000,
    distributing_buy_value_idr=150_000_000,
    distributing_sell_value_idr=700_000_000,
    foreign_buy_lot=9_000,
    foreign_sell_lot=3_000,
    session_turnover_idr=2_200_000_000,
    tier1_net_buyers=1,
    retail_net_buyers=1,
    tier1_net_lot=120,
    retail_net_lot=80,
    # Trailing drift chosen so trend reports UP and the real detector reports
    # phase EXHAUSTION.
    pullback_sessions=30,
    pullback_step="1.2",
    # Below the frozen LiquidityGate third-liner market-cap cap.
    fundamentals=ProbeFundamentals(piotroski_f_score=6, market_cap_idr=310_000_000_000),
    shareholding=ProbeShareholding(institution_pct=28.0, individual_pct=72.0, top_holder_pct=41.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
)

_LOW_FREE_FLOAT = ProbeTicker(
    ticker="PRBG",
    candle_sessions=260,
    base_price=3_200,
    price_step="1.1",
    daily_volume=6_500_000,
    broker_sessions=10,
    net_buy_pattern=(True, True, True, True, False),
    accumulating_buy_value_idr=11_000_000_000,
    accumulating_sell_value_idr=1_600_000_000,
    distributing_buy_value_idr=1_300_000_000,
    distributing_sell_value_idr=6_800_000_000,
    foreign_buy_lot=60_000,
    foreign_sell_lot=11_000,
    session_turnover_idr=35_000_000_000,
    tier1_net_buyers=2,
    retail_net_buyers=1,
    tier1_net_lot=800,
    retail_net_lot=-150,
    fundamentals=ProbeFundamentals(piotroski_f_score=7, market_cap_idr=48_000_000_000_000),
    # free_float_pct = institution + individual, below the frozen
    # FreeFloatGate minimum.
    shareholding=ProbeShareholding(institution_pct=4.0, individual_pct=8.0, top_holder_pct=93.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
)

_NO_ENRICHMENT = ProbeTicker(
    ticker="PRBH",
    candle_sessions=260,
    base_price=1_150,
    price_step="0.7",
    daily_volume=5_500_000,
    broker_sessions=10,
    net_buy_pattern=(True, True, False, True),
    accumulating_buy_value_idr=7_500_000_000,
    accumulating_sell_value_idr=2_100_000_000,
    distributing_buy_value_idr=1_700_000_000,
    distributing_sell_value_idr=5_500_000_000,
    foreign_buy_lot=41_000,
    foreign_sell_lot=17_000,
    session_turnover_idr=24_000_000_000,
    tier1_net_buyers=1,
    retail_net_buyers=1,
    tier1_net_lot=450,
    retail_net_lot=200,
    fundamentals=None,
    shareholding=None,
    bandar=None,
)

_SHORT_BROKER_HISTORY = ProbeTicker(
    ticker="PRBI",
    candle_sessions=40,
    base_price=760,
    price_step="0.3",
    daily_volume=2_000_000,
    broker_sessions=1,
    net_buy_pattern=(True,),
    accumulating_buy_value_idr=1_100_000_000,
    accumulating_sell_value_idr=300_000_000,
    distributing_buy_value_idr=200_000_000,
    distributing_sell_value_idr=900_000_000,
    foreign_buy_lot=6_000,
    foreign_sell_lot=1_500,
    session_turnover_idr=3_000_000_000,
    tier1_net_buyers=1,
    retail_net_buyers=0,
    tier1_net_lot=90,
    retail_net_lot=0,
    fundamentals=ProbeFundamentals(piotroski_f_score=6, market_cap_idr=4_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=35.0, individual_pct=65.0, top_holder_pct=39.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
)

_NO_CANDLES = ProbeTicker(
    ticker="PRBJ",
    candle_sessions=0,
    base_price=500,
    price_step="0",
    daily_volume=0,
    broker_sessions=10,
    net_buy_pattern=(True, False),
    accumulating_buy_value_idr=2_400_000_000,
    accumulating_sell_value_idr=600_000_000,
    distributing_buy_value_idr=500_000_000,
    distributing_sell_value_idr=2_000_000_000,
    foreign_buy_lot=14_000,
    foreign_sell_lot=5_000,
    session_turnover_idr=6_000_000_000,
    tier1_net_buyers=0,
    retail_net_buyers=2,
    tier1_net_lot=0,
    retail_net_lot=120,
    fundamentals=ProbeFundamentals(piotroski_f_score=4, market_cap_idr=2_500_000_000_000),
    shareholding=ProbeShareholding(institution_pct=22.0, individual_pct=78.0, top_holder_pct=37.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
)

# ── Gap-closing archetypes: one per measured mutation gap ───────────────────
# Each of the four tickers below was added to close exactly one named surviving
# mutant recorded by the slice-2 mutation suite. Their numbers are tuned so the
# targeted constant is actually *compared* on the accum decision path; changing
# any of them is a deliberate cohort boundary (ADR-068 §3).

_RSI_EXTENDED = ProbeTicker(
    # Closes phase.thresholds.exhaustion_rsi_min. EXHAUSTION is a conjunction of
    # RSI and price extension; every earlier probe reached it through the price
    # leg with RSI pinned at 100 by a monotone series, so the RSI comparison was
    # never decisive. This tail oscillates: RSI settles at ~67.9 (inside the
    # mutated 30 band, outside the frozen 72 band) while 20-session extension
    # stays above the 8% price leg, so only the RSI threshold decides.
    ticker="PRBK",
    candle_sessions=260,
    base_price=900,
    price_step="0",
    daily_volume=7_000_000,
    broker_sessions=10,
    net_buy_pattern=(True, True, False, True),
    accumulating_buy_value_idr=8_000_000_000,
    accumulating_sell_value_idr=2_000_000_000,
    distributing_buy_value_idr=1_600_000_000,
    distributing_sell_value_idr=6_000_000_000,
    foreign_buy_lot=44_000,
    foreign_sell_lot=15_000,
    session_turnover_idr=26_000_000_000,
    tier1_net_buyers=2,
    retail_net_buyers=1,
    tier1_net_lot=650,
    retail_net_lot=-120,
    fundamentals=ProbeFundamentals(piotroski_f_score=7, market_cap_idr=29_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=49.0, individual_pct=51.0, top_holder_pct=44.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
    tail=ProbeCandleTail(sessions=80, close_deltas=("34", "30", "-27", "0"), body="1"),
)

_BB_MID_BAND = ProbeTicker(
    # Closes phase.thresholds.compression_max_bb_width_pctile. A monotone series
    # produces a constant band width, so its percentile rank is always 1.0 and
    # the compression threshold is never decisive. This tail steps volatility
    # down in three regimes, leaving the current width at ~0.73 of the trailing
    # 60-session distribution: above the frozen 0.20 (not COMPRESSION today),
    # below the mutated 0.90 (COMPRESSION once mutated).
    ticker="PRBL",
    candle_sessions=260,
    base_price=1_200,
    price_step="0.5",
    daily_volume=6_500_000,
    broker_sessions=10,
    net_buy_pattern=(True, False, True, True),
    accumulating_buy_value_idr=7_500_000_000,
    accumulating_sell_value_idr=2_300_000_000,
    distributing_buy_value_idr=1_800_000_000,
    distributing_sell_value_idr=5_800_000_000,
    foreign_buy_lot=39_000,
    foreign_sell_lot=18_000,
    session_turnover_idr=25_000_000_000,
    tier1_net_buyers=1,
    retail_net_buyers=2,
    tier1_net_lot=420,
    retail_net_lot=180,
    fundamentals=ProbeFundamentals(piotroski_f_score=6, market_cap_idr=24_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=46.0, individual_pct=54.0, top_holder_pct=43.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
    tail=ProbeCandleTail(
        # Three volatility regimes, widest first, so the trailing 60-session
        # width distribution has real spread and the current width lands in its
        # upper-middle rather than at either extreme.
        sessions=180,
        close_deltas=(
            *(("14", "-14") * 4),
            *(("6", "-6") * 4),
            *(("3", "-3") * 4),
        ),
        body="0",
    ),
)

_VOLUME_DRY_UP_EXPANSION = ProbeTicker(
    # Closes phase.volume_trigger.min_valid_20d_sessions. Every earlier probe
    # used one constant volume for every session, so dry-up and expansion ratios
    # were both exactly 1.0, the trigger never confirmed, and the valid-session
    # count could not change any phase. This six-session volume cycle (five quiet
    # sessions then one 8x expansion, landing on the latest session with a
    # positive body) confirms the trigger, so BREAKOUT_CONFIRMATION depends on
    # the volume-validity rule the mutant perturbs.
    ticker="PRBM",
    candle_sessions=260,
    base_price=1_200,
    price_step="0.5",
    daily_volume=5_000_000,
    broker_sessions=10,
    net_buy_pattern=(True, True, True, False),
    accumulating_buy_value_idr=8_800_000_000,
    accumulating_sell_value_idr=2_100_000_000,
    distributing_buy_value_idr=1_500_000_000,
    distributing_sell_value_idr=6_400_000_000,
    foreign_buy_lot=47_000,
    foreign_sell_lot=16_000,
    session_turnover_idr=27_000_000_000,
    tier1_net_buyers=2,
    retail_net_buyers=1,
    tier1_net_lot=680,
    retail_net_lot=-140,
    fundamentals=ProbeFundamentals(piotroski_f_score=7, market_cap_idr=31_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=52.0, individual_pct=48.0, top_holder_pct=45.0),
    bandar=ProbeBandar(five_day_accdist="Small Accum"),
    tail=ProbeCandleTail(
        sessions=120,
        close_deltas=("3", "-2", "3", "-2", "2", "1"),
        volumes=(5_000_000, 5_000_000, 5_000_000, 5_000_000, 5_000_000, 40_000_000),
        body="1",
    ),
)

_VALUATION_STRETCHED = ProbeTicker(
    # Closes signal.flags.valuation_stretched.score_penalty. Signal flags read
    # SignalContext, whose forward P/E is derived from provider-supplied forward
    # estimates; no earlier probe wired that provider, so no flag ever fired and
    # the penalty was never subtracted. forward_eps_1y is chosen so the derived
    # forward P/E clears the frozen 50.0 threshold against this ticker's own
    # closing price.
    ticker="PRBN",
    candle_sessions=260,
    base_price=1_300,
    price_step="0.4",
    daily_volume=6_800_000,
    broker_sessions=10,
    net_buy_pattern=(True, True, False, True),
    accumulating_buy_value_idr=9_200_000_000,
    accumulating_sell_value_idr=1_900_000_000,
    distributing_buy_value_idr=1_500_000_000,
    distributing_sell_value_idr=6_600_000_000,
    foreign_buy_lot=51_000,
    foreign_sell_lot=15_000,
    session_turnover_idr=29_000_000_000,
    tier1_net_buyers=3,
    retail_net_buyers=1,
    tier1_net_lot=760,
    retail_net_lot=-160,
    fundamentals=ProbeFundamentals(piotroski_f_score=8, market_cap_idr=41_000_000_000_000),
    shareholding=ProbeShareholding(institution_pct=55.0, individual_pct=45.0, top_holder_pct=47.0),
    bandar=ProbeBandar(five_day_accdist="Big Accum"),
    forward_estimates=ProbeForwardEstimates(forward_eps_1y=20.0, revenue_forward_1y=9_000.0),
    pullback_sessions=8,
    pullback_step="-4",
)

_MIXED_GATE_UNIVERSE = (
    _STRONG_ACCUM,
    _MODERATE_ACCUM,
    _WEAK_FLOW,
    _BANDAR_DISTRIBUTING,
    _DISTRESSED_FUNDAMENTALS,
    _THIRD_LINER,
    _LOW_FREE_FLOAT,
)


def _regime_probe(probe_id: str, regime: str | None, surface: str) -> BehavioralProbe:
    return BehavioralProbe(
        probe_id=probe_id,
        surface=surface,
        tickers=_MIXED_GATE_UNIVERSE,
        regime=regime,
    )


_CORE_PROBES: tuple[BehavioralProbe, ...] = (
    _regime_probe(
        "regime_risk_on_mixed_gates",
        "RISK_ON",
        "RISK_ON regime conditioning across all four risk gates",
    ),
    _regime_probe(
        "regime_neutral_mixed_gates",
        "NEUTRAL",
        "NEUTRAL regime conditioning across all four risk gates",
    ),
    _regime_probe(
        "regime_volatile_mixed_gates",
        "VOLATILE",
        "VOLATILE regime conditioning across all four risk gates",
    ),
    _regime_probe(
        "regime_risk_off_mixed_gates",
        "RISK_OFF",
        "RISK_OFF regime conditioning across all four risk gates",
    ),
    BehavioralProbe(
        probe_id="regime_absent_default_policy",
        surface="No MarketContext — DecisionPolicy default regime branch",
        tickers=_MIXED_GATE_UNIVERSE,
        regime=None,
    ),
    BehavioralProbe(
        probe_id="regime_risk_off_tightened_gates",
        surface="RISK_OFF with gate tightening and reduced size multiplier",
        tickers=_MIXED_GATE_UNIVERSE,
        regime="RISK_OFF",
        regime_conviction=0.25,
        regime_signal_multiplier=0.4,
        regime_gate_tightening=True,
    ),
    BehavioralProbe(
        probe_id="accum_score_threshold_rejection",
        surface="min_accum_score rejection — inclusion/exclusion boundary",
        tickers=_MIXED_GATE_UNIVERSE,
        regime="NEUTRAL",
        min_accum_score=55.0,
        min_accum_score_enabled=True,
    ),
    BehavioralProbe(
        probe_id="signal_score_threshold_rejection",
        surface="min_signal_score rejection — signal gate ordering",
        tickers=_MIXED_GATE_UNIVERSE,
        regime="NEUTRAL",
        min_signal_score=55.0,
        min_signal_score_enabled=True,
    ),
    BehavioralProbe(
        probe_id="structural_filter_market_cap_and_piotroski",
        surface="Structural pre-filter rejections before enrichment",
        tickers=_MIXED_GATE_UNIVERSE,
        regime="NEUTRAL",
        min_market_cap_idr=10_000_000_000_000,
        min_piotroski=6,
    ),
    BehavioralProbe(
        probe_id="missing_enrichment_evidence",
        surface="No enrichment providers — gate missing-data branches",
        tickers=(_STRONG_ACCUM, _MODERATE_ACCUM, _NO_ENRICHMENT),
        regime="NEUTRAL",
        enrichment_providers_enabled=False,
    ),
    BehavioralProbe(
        probe_id="unresolved_source_availability",
        surface="No availability authority — zero evidence-coverage branch",
        tickers=_MIXED_GATE_UNIVERSE,
        regime="RISK_ON",
        source_availability_enabled=False,
    ),
    BehavioralProbe(
        probe_id="insufficient_history_skips",
        surface="Evaluator skips: short broker window and absent candles",
        tickers=(_STRONG_ACCUM, _SHORT_BROKER_HISTORY, _NO_CANDLES),
        regime="NEUTRAL",
        min_net_buy_days=2,
    ),
    BehavioralProbe(
        probe_id="short_window_three_sessions",
        surface="window_days=3 — window selection and streak arithmetic",
        tickers=_MIXED_GATE_UNIVERSE,
        regime="RISK_ON",
        window_days=3,
        min_net_buy_days=1,
    ),
    BehavioralProbe(
        probe_id="long_window_ten_sessions",
        surface="window_days=10 — full frozen broker history",
        tickers=_MIXED_GATE_UNIVERSE,
        regime="RISK_ON",
        window_days=10,
    ),
    BehavioralProbe(
        probe_id="single_ticker_deep_judgment",
        surface="Single-ticker screen path (sector-macro attachment branch)",
        tickers=(_STRONG_ACCUM,),
        regime="NEUTRAL",
    ),
    # ── Gap-closing core probes (deliberate cohort boundary) ────────────────
    # Each runs its dedicated archetype beside _STRONG_ACCUM so the probe still
    # exercises ordering/inclusion, and each closes exactly one named surviving
    # mutant from the slice-2 record.
    BehavioralProbe(
        probe_id="phase_exhaustion_via_rsi_band",
        surface="EXHAUSTION reached through the RSI leg, not the price-extension leg",
        tickers=(_STRONG_ACCUM, _RSI_EXTENDED),
        regime="NEUTRAL",
    ),
    BehavioralProbe(
        probe_id="phase_compression_bb_width_band",
        surface="Band-width percentile inside the COMPRESSION comparison band",
        tickers=(_STRONG_ACCUM, _BB_MID_BAND),
        regime="NEUTRAL",
    ),
    BehavioralProbe(
        probe_id="phase_breakout_volume_dry_up_expansion",
        surface="Confirmed volume dry-up then expansion — volume-validity branch",
        tickers=(_STRONG_ACCUM, _VOLUME_DRY_UP_EXPANSION),
        regime="NEUTRAL",
    ),
    BehavioralProbe(
        probe_id="signal_flag_valuation_stretched",
        surface="Forward-estimate evidence firing the valuation_stretched flag penalty",
        tickers=(_STRONG_ACCUM, _VALUATION_STRETCHED),
        regime="NEUTRAL",
    ),
)

# ── Extended probes (coverage / mutation material only) ─────────────────────
# ADR-068 §3: these must never enter identity. They exist to reach branches the
# frozen core set cannot, so a mutation there is *measured and named* instead of
# invisible. Every extended probe below mirrors a core probe's universe and only
# adds the swing setup catalog, keeping the delta attributable to one input.

_EXTENDED_PROBES: tuple[BehavioralProbe, ...] = (
    BehavioralProbe(
        probe_id="ext_setup_family_neutral_mixed_gates",
        surface="NEUTRAL with setup families attached — readiness and family branches",
        tickers=_MIXED_GATE_UNIVERSE,
        regime="NEUTRAL",
        swing_setup_families_enabled=True,
    ),
    BehavioralProbe(
        probe_id="ext_setup_family_risk_off_tightened_gates",
        surface="RISK_OFF tightened with setup families — setup/regime action branches",
        tickers=_MIXED_GATE_UNIVERSE,
        regime="RISK_OFF",
        regime_conviction=0.25,
        regime_signal_multiplier=0.4,
        regime_gate_tightening=True,
        swing_setup_families_enabled=True,
    ),
    BehavioralProbe(
        probe_id="ext_setup_family_regime_absent",
        surface="No MarketContext with setup families — default-regime family branch",
        tickers=_MIXED_GATE_UNIVERSE,
        regime=None,
        swing_setup_families_enabled=True,
    ),
    BehavioralProbe(
        probe_id="ext_setup_family_single_ticker_deep",
        surface="Single-ticker screen with setup families attached",
        tickers=(_STRONG_ACCUM,),
        regime="NEUTRAL",
        swing_setup_families_enabled=True,
    ),
)


def core_probe_set() -> tuple[BehavioralProbe, ...]:
    """Return the frozen core probe set — the only identity-material probes."""
    return _CORE_PROBES


def extended_probe_set() -> tuple[BehavioralProbe, ...]:
    """Return the extended probe set — coverage/mutation material only.

    ADR-068 §3: adding an extended probe must never move cohort identity.
    """
    return _EXTENDED_PROBES
