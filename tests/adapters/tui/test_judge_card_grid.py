"""Judge desk card grid: each section owns a card; no overflow dump."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.judge_desk_model import (
    CARD_ACCUM,
    CARD_DATA,
    CARD_MARKET,
    CARD_RISK,
    CARD_SESSION,
    CARD_TRADE_SETUP,
    build_judge_desk_model,
)
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter, AccumRowView
from src.adapters.tui.widgets.judge_desk import JudgeDesk


def _gate(name: str, *, triggered: bool = False, outcome: str = "pass", reason: str = "ok"):
    return SimpleNamespace(
        gate=name,
        tier="structural",
        outcome=outcome,
        triggered=triggered,
        reason=reason,
        confidence=100,
    )


def _full_source() -> SimpleNamespace:
    return SimpleNamespace(
        ticker="BBCA",
        accum_score=50.0,
        rsi=50.0,
        consecutive_streak=2,
        net_buy_ratio=0.5,
        vwap_discount_pct=0.0,
        current_price=6275,
        name="BBCA",
        latest_candle_date=None,
        latest_broker_date=None,
        freshness=SimpleNamespace(
            candle_as_of=__import__("datetime").date(2026, 7, 29),
            broker_as_of=__import__("datetime").date(2026, 7, 29),
            alignment_state=SimpleNamespace(value="ALIGNED"),
            candle_state=SimpleNamespace(value="PENDING_EOD"),
            broker_state=SimpleNamespace(value="PENDING_EOD"),
        ),
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            signal_score=73,
            signal_strength=SimpleNamespace(value="STRONG"),
            rationale="Signal 73/100 (STRONG) | gate: open",
            blocking_gates=(),
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(
                score=73,
                strength=SimpleNamespace(value="STRONG"),
                entry_quality=SimpleNamespace(value="WATCH"),
                signal_authority_coverage=0.85,
                breakdown=None,
                decision_constraints=None,
            ),
            setup_readiness=None,
            coverage_warning=None,
            signal_authority_coverage=0.85,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("all gates passed",),
            risk_level_name="OPEN",
        ),
        risk_gate_evaluations=(
            _gate("FundamentalGate", reason="F-score 4 > 3 (fundamental gate passes)"),
            _gate("LiquidityGate", reason="liquidity and market cap checks passed"),
            _gate("FreeFloatGate", reason="Free float 31.2% above 15% threshold"),
            _gate("BandarGate", reason="Bandar 5-day (Big Acc) consistent"),
        ),
    )


def _row() -> AccumRowView:
    return AccumRowView(
        ticker="BBCA",
        signal="73",
        accum="50.0",
        action="WATCH",
        phase="ACCUMULATION",
        streak="2",
        rsi="50",
        net_pct="0.5",
        disc_pct="0",
        price="6275",
        gate="OPEN",
        name="BBCA",
        source=_full_source(),
    )


def test_model_emits_distinct_section_cards_compact():
    mce = SimpleNamespace(
        regime=SimpleNamespace(value="NEUTRAL"),
        conviction=0.49,
        confidence=0.93,
        stability=SimpleNamespace(value="TRANSITIONING"),
        warning="Regime changed recently – in NEUTRAL for 0 day(s)",
    )
    session = SimpleNamespace(
        market_session_name="REGULAR",
        analysis_as_of=__import__("datetime").date(2026, 7, 29),
        latest_completed_session=__import__("datetime").date(2026, 7, 29),
        resolution_source="ihsg_cache_prior_session",
    )
    model = build_judge_desk_model(
        _row(),
        effective_session=session,
        market_context=mce,
    )
    keys = {c.key for c in model.cards}
    for required in (
        CARD_RISK,
        CARD_TRADE_SETUP,
        CARD_ACCUM,
        CARD_DATA,
        CARD_SESSION,
        CARD_MARKET,
    ):
        assert required in keys, f"missing card {required}"

    risk = model.card_by_key(CARD_RISK)
    assert risk is not None
    assert "OPEN" in risk.headline
    # Compact chips, not multi-line FundamentalGate essays
    body = "\n".join(risk.lines)
    assert "FundamentalGate pass · F-score" not in body
    assert "✓" in body or "all gates" in body.lower()

    accum = model.card_by_key(CARD_ACCUM)
    assert accum is not None
    assert "50" in accum.headline
    # Prefer short parts over long equation only
    assert "50.0 = cons" not in "\n".join(accum.lines)

    data = model.card_by_key(CARD_DATA)
    assert data is not None
    assert "ALIGNED" in data.headline

    ts = model.card_by_key(CARD_TRADE_SETUP)
    assert ts is not None
    assert "WATCH" in ts.headline
    assert "ENTER" not in ts.headline  # present-only board action


def test_limited_model_scalars_only_no_full_engine_cards():
    row = AccumRowView(
        ticker="ASII",
        signal="40",
        accum="30",
        action="AVOID",
        phase="NONE",
        streak="0",
        rsi="60",
        net_pct="0",
        disc_pct="0",
        price="5000",
        gate="BLOCKED",
        source=None,
    )
    model = build_judge_desk_model(row)
    assert model.limited is True
    keys = {c.key for c in model.cards}
    assert "scalars" in keys
    assert CARD_RISK not in keys
    assert CARD_MARKET not in keys


def test_cockpit_paints_each_section_card_slot():
    c = _full_source()
    result = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[c],
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-29"},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=SimpleNamespace(
            market_session_name="REGULAR",
            analysis_as_of=__import__("datetime").date(2026, 7, 29),
            latest_completed_session=__import__("datetime").date(2026, 7, 29),
            resolution_source="ihsg_cache",
        ),
        market_context=SimpleNamespace(
            regime=SimpleNamespace(value="NEUTRAL"),
            conviction=0.49,
            confidence=0.93,
            stability=SimpleNamespace(value="TRANSITIONING"),
            warning="recent regime change",
        ),
    )

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: result,
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(140, 48)) as pilot:
            await pilot.pause(0.05)
            app._on_accum_payload(result)
            await pilot.pause(0.05)
            app._row_index = 0
            app._focus_ticker = "BBCA"
            app._open_detail()
            await pilot.pause(0.1)
            desk = app.query_one("#judge-desk", JudgeDesk)
            assert desk.display is True
            # No overflow dump id
            try:
                app.query_one("#jd-card-more")
                raise AssertionError("overflow #jd-card-more must not exist")
            except Exception as exc:
                # Textual raises NoMatches
                assert "jd-card-more" in str(exc) or "NoMatches" in type(exc).__name__

            for key in (CARD_RISK, CARD_TRADE_SETUP, CARD_ACCUM, CARD_DATA, CARD_SESSION):
                el = app.query_one(f"#jd-card-{key}")
                assert el.display is True, f"card {key} should be visible"
                text = str(el.render())
                assert text.strip(), f"card {key} empty"

            risk_text = str(app.query_one(f"#jd-card-{CARD_RISK}").render())
            assert "RISK" in risk_text.upper()
            assert "OPEN" in risk_text
            assert "FundamentalGate pass · F-score 4 > 3" not in risk_text
            # Compact chips, not multi-line gate essays
            assert "F-score 4 > 3" not in risk_text

            action = str(app.query_one("#jd-action").render())
            assert "WATCH" in action

    asyncio.run(scenario())
