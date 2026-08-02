"""Non-authoritative transcript card for one optional agent turn."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from src.application.dto.accumulation_agent import AgentTurnResult, AgentTurnStatus


class AgentCommentary(Vertical):
    """Display model commentary without borrowing deterministic verdict styling."""

    DEFAULT_CSS = """
    AgentCommentary {
        display: none;
        height: auto;
        width: 100%;
        margin-bottom: 1;
        padding: 1 2;
        background: #101014;
        border: solid #24242c;
        border-left: solid #686878;
    }
    AgentCommentary .agent-title { color: #aaaabc; text-style: bold; }
    AgentCommentary .agent-answer { color: #d0d0d8; height: auto; margin-top: 1; }
    AgentCommentary .agent-meta { color: #686878; height: auto; margin-top: 1; }
    AgentCommentary .agent-warning { color: #d4b06a; height: auto; }
    AgentCommentary .agent-error { color: #c97a72; height: auto; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("Agent commentary", classes="agent-title")
        yield Static("", classes="agent-answer")
        yield Static("", classes="agent-meta")
        yield Static("", classes="agent-warning")
        yield Static("", classes="agent-error")

    def clear(self) -> None:
        self.display = False
        for selector in (".agent-answer", ".agent-meta", ".agent-warning", ".agent-error"):
            self.query_one(selector, Static).update("")

    def show_loading(self, *, provider: str, ticker: str) -> None:
        self.display = True
        self.query_one(".agent-answer", Static).update("Thinking…")
        self.query_one(".agent-meta", Static).update(Text(f"remote · {provider} · {ticker}"))
        self.query_one(".agent-warning", Static).update("")
        self.query_one(".agent-error", Static).update("")

    def show_result(self, result: AgentTurnResult, *, as_of: str) -> None:
        self.display = True
        answer = result.answer if result.status is AgentTurnStatus.SUCCESS else ""
        self.query_one(".agent-answer", Static).update(Text(answer))
        meta = ""
        if result.status is AgentTurnStatus.SUCCESS:
            meta = (
                f"{result.provider} · {result.model} · as-of {as_of}\n"
                f"context {result.context_reference}"
            )
        self.query_one(".agent-meta", Static).update(Text(meta))
        warnings = "\n".join(f"Warning: {item}" for item in result.warnings)
        self.query_one(".agent-warning", Static).update(Text(warnings))
        self.query_one(".agent-error", Static).update(Text(result.error_message or ""))
