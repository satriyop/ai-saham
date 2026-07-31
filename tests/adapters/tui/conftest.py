"""Directory-scoped pytest config for the TUI adapter tests.

Every test here mounts and paints a real Textual app (~1.5-4.7s each) — the
heaviest slice of the suite, ~60% of full-suite wall time. Auto-tag them all
`tui` so the fast dev loop can skip the slice with `pytest -m "not tui"` while
CI still runs everything. The marker is registered in pyproject.toml.

This is a stopgap for the inner loop; the durable fix is to push most of these
assertions down to widget/view-model unit tests so full-app mounts become a
handful of e2e journeys — see
tasks/backlog/lighten_tui_full_app_test_weight.md.
"""

from pathlib import Path

import pytest

_TUI_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items):
    """Tag every collected item under this directory with the `tui` marker.

    The hook receives the whole session's items, so filter by path — only tests
    physically under tests/adapters/tui are marked.
    """
    for item in items:
        if _TUI_DIR in Path(item.fspath).parents:
            item.add_marker(pytest.mark.tui)
