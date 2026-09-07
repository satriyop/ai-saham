"""Suite-wide pytest hooks.

CI GitHub runners enable Rich color on an 80-column pty. Typer then splits
``--flag`` as ``-`` + ANSI + ``-flag``, so substring asserts like
``"--universe" in result.stdout`` fail on CI while passing on a wide local
terminal. Force a colorless, wide help layout for every test.
"""

from __future__ import annotations

import os

os.environ["NO_COLOR"] = "1"
os.environ.pop("FORCE_COLOR", None)
os.environ["COLUMNS"] = "120"
