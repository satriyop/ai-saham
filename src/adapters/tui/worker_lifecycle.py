"""Safe UI-thread dispatch for cancellable Textual thread workers.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual.app import App
from textual.worker import get_current_worker


def dispatch_if_active(
    app: App,
    callback: Callable[..., Any],
    *args: Any,
) -> object | None:
    """Drop delivery after cancellation/exit; preserve unexpected runtime errors."""
    worker = get_current_worker()
    if worker.is_cancelled:
        return None
    try:
        return app.call_from_thread(callback, *args)
    except RuntimeError:
        if worker.is_cancelled or not app.is_running:
            return None
        raise
