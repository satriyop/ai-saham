"""Unit tests for screen deep evidence (ADR-054 S1) — no Action mutation."""

from datetime import date
from types import SimpleNamespace

from src.application.services.screen_judgment_deep_evidence import (
    ScreenJudgmentDeepEvidenceRequest,
    collect_screen_judgment_deep_evidence,
    deep_evidence_action_fingerprint,
)


def test_deep_flags_any_enabled():
    assert not ScreenJudgmentDeepEvidenceRequest().any_enabled
    assert ScreenJudgmentDeepEvidenceRequest(include_flow_detail=True).any_enabled
    assert ScreenJudgmentDeepEvidenceRequest(include_full=True).wants_flow
    assert ScreenJudgmentDeepEvidenceRequest(include_full=True).wants_sentiment


def test_collect_does_not_require_candidate_trade_setup():
    bag = collect_screen_judgment_deep_evidence(
        ticker="bbca",
        as_of_date=date(2026, 7, 1),
        candidate=None,
        flags=ScreenJudgmentDeepEvidenceRequest(include_flow_detail=True),
        build_flow_detail=lambda **kw: SimpleNamespace(
            window_sessions=30, to_dict=lambda: {"window": 30}
        ),
    )
    assert bag.ticker == "BBCA"
    assert bag.flow_detail is not None
    assert bag.to_dict()["flow_detail"] == {"window": 30}


def test_collect_setup_and_sentiment_fail_soft():
    bag = collect_screen_judgment_deep_evidence(
        ticker="BBRI",
        as_of_date=date(2026, 7, 1),
        candidate=SimpleNamespace(
            trade_setup=SimpleNamespace(action=SimpleNamespace(value="WATCH"))
        ),
        flags=ScreenJudgmentDeepEvidenceRequest(
            setup_name="foreign-bounce",
            include_sentiment=True,
        ),
        evaluate_setup=lambda name, cand: (_ for _ in ()).throw(RuntimeError("boom")),
        fetch_sentiment=lambda **kw: (_ for _ in ()).throw(RuntimeError("net")),
    )
    assert bag.setup_eval is None
    assert any("Setup lens" in w for w in bag.warnings)
    assert bag.sentiment_warning is not None


def test_action_fingerprint_stable():
    cand = SimpleNamespace(trade_setup=SimpleNamespace(action=SimpleNamespace(value="WATCH")))
    assert deep_evidence_action_fingerprint(cand) == "WATCH"
    assert deep_evidence_action_fingerprint(None) is None


def test_collect_preserves_action_fingerprint_when_evidence_runs():
    cand = SimpleNamespace(trade_setup=SimpleNamespace(action=SimpleNamespace(value="ENTER")))
    before = deep_evidence_action_fingerprint(cand)
    collect_screen_judgment_deep_evidence(
        ticker="BBCA",
        as_of_date=date(2026, 7, 1),
        candidate=cand,
        flags=ScreenJudgmentDeepEvidenceRequest(
            include_flow_detail=True,
            include_sentiment=True,
            setup_name="foreign-bounce",
        ),
        build_flow_detail=lambda **kw: SimpleNamespace(to_dict=lambda: {}),
        evaluate_setup=lambda name, c: SimpleNamespace(
            match=SimpleNamespace(value="MATCH"),
            gates=(),
            failed_reasons=(),
            to_dict=lambda: {"match": "MATCH"},
        ),
        fetch_sentiment=lambda **kw: (None, "skip"),
    )
    assert deep_evidence_action_fingerprint(cand) == before
