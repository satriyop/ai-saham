"""Directory-scoped pytest config for the TUI adapter tests.

The `tui` marker means *cost*, not *location*: a test earns it by mounting and
driving a real Textual app, which is the expensive part (~1.5-4.7s each; the
full-app slice is ~60% of full-suite wall time). This directory holds a MIX —
full-app journeys AND pure model/paint unit tests (e.g. test_*_model.py,
test_board_snapshot.py) sitting in the same tree, sometimes in the same file
(test_cockpit_app.py has both). So we cannot tag by path.

Auto-detection: a test is tagged `tui` iff its source drives a Textual app via
`run_test` (the canonical mount-and-drive entrypoint). Pure model/paint tests
have no `run_test`, so they stay in the fast loop automatically. Fast loop:
`pytest -m "not tui"`; heavy slice: `pytest -m tui`.

Explicit overrides (rare, for cases auto-detection gets wrong):
- `@pytest.mark.tui`      force-include in the heavy slice
- `@pytest.mark.tui_unit` force-exclude (converted to a pure unit; never mounts)

Both markers are registered in pyproject.toml. Durable plan to shrink the
full-app slice: tasks/backlog/lighten_tui_full_app_test_weight.md.
"""

import inspect
from pathlib import Path

import pytest

_TUI_DIR = Path(__file__).parent


def _drives_textual_app(item: pytest.Item) -> bool:
    """True when the test's own source mounts a Textual app via ``run_test``.

    ``inspect.getsource`` on the test function includes its nested helper defs,
    which is where these tests place ``async with app.run_test(...)``.
    """
    func = getattr(item, "function", None)
    if func is None:
        return False
    try:
        return "run_test" in inspect.getsource(func)
    except (OSError, TypeError):
        return False


def pytest_collection_modifyitems(items):
    for item in items:
        if _TUI_DIR not in Path(item.fspath).parents:
            continue
        if item.get_closest_marker("tui_unit"):
            continue  # explicit opt-out: a converted pure/model test
        if item.get_closest_marker("tui") or _drives_textual_app(item):
            item.add_marker(pytest.mark.tui)
