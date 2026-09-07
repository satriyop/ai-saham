"""Suite-wide pytest hooks.

CI GitHub runners enable Rich color inside Typer's CliRunner even when
``NO_COLOR`` is set. Help then emits ``-`` + ANSI + ``-flag``, so
``"--universe" in result.stdout`` fails on CI and passes on a wide local
terminal. Strip ANSI on captured CLI results so substring asserts see
``--flag``.
"""

from __future__ import annotations

import os
import re

from typer.testing import Result

os.environ["NO_COLOR"] = "1"
os.environ.pop("FORCE_COLOR", None)
os.environ["COLUMNS"] = "120"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _decode(self: Result, data: bytes) -> str:
    return data.decode(self.runner.charset, "replace").replace("\r\n", "\n")


Result.stdout = property(lambda self: _plain(_decode(self, self.stdout_bytes)))  # type: ignore[method-assign]
Result.stderr = property(lambda self: _plain(_decode(self, self.stderr_bytes)))  # type: ignore[method-assign]
Result.output = property(lambda self: _plain(_decode(self, self.output_bytes)))  # type: ignore[method-assign]
