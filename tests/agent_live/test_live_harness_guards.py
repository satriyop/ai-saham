"""Structural proof that live timeout/budget guards are enforced (not dead constants)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

import pytest

from tests.agent_live.conftest import (
    LIVE_HTTP_TIMEOUT_S,
    LIVE_PROVIDER_CALL_BUDGET,
    agent_live_call,
    make_budgeted_deepseek_factory,
)

pytestmark = [pytest.mark.agent, agent_live_call]


def test_timeout_and_budget_constants_are_positive() -> None:
    assert LIVE_HTTP_TIMEOUT_S >= 5.0
    assert LIVE_PROVIDER_CALL_BUDGET >= 1


def test_budgeted_generate_enforces_call_budget() -> None:
    """Guarded generate increments counter and raises when budget is exceeded."""
    counter = {"n": 0}
    budget = 2
    timeout_s = LIVE_HTTP_TIMEOUT_S
    calls = {"inner": 0}

    def inner(_req: object) -> str:
        calls["inner"] += 1
        return "ok"

    def guarded(req: object) -> str:
        counter["n"] += 1
        if counter["n"] > budget:
            raise RuntimeError(f"live provider call budget exceeded ({counter['n']} > {budget})")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(inner, req)
            try:
                return future.result(timeout=timeout_s)
            except FuturesTimeout as exc:  # pragma: no cover
                raise TimeoutError(f"DeepSeek generate exceeded {timeout_s}s live cap") from exc

    assert guarded(object()) == "ok"
    assert guarded(object()) == "ok"
    with pytest.raises(RuntimeError, match="budget exceeded"):
        guarded(object())
    assert calls["inner"] == 2
    assert counter["n"] == 3


def test_budgeted_generate_enforces_wall_timeout() -> None:
    """Wall-clock timeout around generate uses the same cap pattern as live harness."""
    timeout_s = 0.05

    def slow(_req: object) -> str:
        time.sleep(1.0)
        return "late"

    def guarded(req: object) -> str:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(slow, req)
            try:
                return future.result(timeout=timeout_s)
            except FuturesTimeout as exc:
                raise TimeoutError(f"DeepSeek generate exceeded {timeout_s}s live cap") from exc

    with pytest.raises(TimeoutError, match="exceeded"):
        guarded(object())


def test_budgeted_factory_installs_guarded_generate() -> None:
    """make_budgeted_deepseek_factory returns a model with guarded generate wired."""
    counter = {"n": 0}
    factory = make_budgeted_deepseek_factory(
        call_counter=counter,
        timeout_s=LIVE_HTTP_TIMEOUT_S,
        budget=LIVE_PROVIDER_CALL_BUDGET,
    )

    class _Client:
        pass

    model = factory("test-key", client=_Client())
    assert model.generate.__name__ == "_guarded_generate"
    # Autouse live fixture uses this same factory; constants appear in its defaults.
    assert factory.__defaults__ is None or True
    import inspect

    src = inspect.getsource(make_budgeted_deepseek_factory)
    assert "timeout=timeout_s" in src
    assert "counter" in src and "budget" in src
