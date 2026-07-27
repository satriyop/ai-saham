"""
OpeningTuneUseCase — AI-powered config tuning from the opening session accuracy grade.

Calls DeepSeek with the grade report + current config values and asks for specific
parameter change recommendations. Saves both structured JSON and a markdown narrative.

Layer: Application
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

OPENING_DATA_DIR = Path("data/opening")

TUNE_SYSTEM_PROMPT = """\
You are a quantitative analyst specializing in Indonesian equity markets (IDX/IHSG).

You will receive today's accuracy report for a pre-open screener (IDX call auction, 08:45-09:00
WIB).
The screener selects stocks to trade at the 09:00 WIB opening auction and predicts entry price
ranges.

Your task: identify where the screener succeeded and failed based on the data, then suggest
specific, evidence-based changes to the configuration parameters.

Rules:
- Ground EVERY recommendation in specific numbers from the report. No generic advice.
- If clean_trade_rate for ENTER > WATCH, the TradeSetup selection logic works — focus on
positioning.
- If entry_range_hit_rate is low, focus on ATR cap parameters.
- If trend accuracy drops significantly from T5→T30, note momentum sustainability issues.
- "1R" = one risk unit = entry_price - atr_stop. clean_trade = 1R reached before stop.
- bid_pressure_preopen: NCP-locked (08:57 WIB) order book imbalance =
bid_lots/(bid_lots+offer_lots). >0.6 = committed buyers, <0.4 = sellers dominating.
- bid_pressure_T0: same metric at 09:00 (first post-open reading).
- bid_momentum: bid_pressure_T5 - bid_pressure_T0. Positive = buying pressure increased after open.
- Research basis: order flow imbalance is the most empirically validated short-horizon return
predictor (Quantitative Finance, 2023).

Output format — respond with EXACTLY this structure:
```json
{
  "summary": "1-2 sentence summary of today's screener performance",
  "top_finding": "The single most important pattern observed",
  "config_recommendations": {
    "pre_open_screener.yaml": {
      "param.path": {"current": <value>, "suggested": <value>, "reason": "<evidence-based reason>"}
    }
  },
  "watch_next_session": ["pattern 1 to watch", "pattern 2 to watch"]
}
```
Then add a markdown narrative section after the JSON block.
"""


@dataclass(frozen=True)
class OpeningTuneRequest:
    run_date: date | None = None
    deepseek_api_key: str | None = None
    allow_invalid_snapshot: bool = False


class OpeningTuneUseCase:
    """Call DeepSeek with today's accuracy grade and save config recommendations."""

    def execute(self, request: OpeningTuneRequest) -> dict:
        today = request.run_date or date.today()
        day_dir = OPENING_DATA_DIR / today.strftime("%Y%m%d")
        grade_path = day_dir / "grade.json"

        if not grade_path.exists():
            return {"skipped": True, "reason": f"grade.json not found at {grade_path}"}

        with open(grade_path) as f:
            grade = json.load(f)

        invalid_reason = _invalid_snapshot_reason(grade)
        if invalid_reason and not request.allow_invalid_snapshot:
            return {
                "skipped": True,
                "reason": invalid_reason,
                "requires_override": "--allow-invalid-snapshot",
            }

        user_prompt = _build_user_prompt(grade)

        raw_text, tokens_used = _call_deepseek(
            system_prompt=TUNE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            api_key=request.deepseek_api_key,
        )

        json_block, markdown_narrative = _parse_response(raw_text)

        tune = {
            "analysis_at": _now_iso(),
            "session_date": str(today),
            "clean_trade_rate": grade.get("clean_trade_rate"),
            "entry_range_hit_rate": grade.get("entry_range_hit_rate"),
            "tokens_used": tokens_used,
            "config_recommendations": json_block.get("config_recommendations", {}),
            "summary": json_block.get("summary"),
            "top_finding": json_block.get("top_finding"),
            "watch_next_session": json_block.get("watch_next_session", []),
            "narrative_path": str(day_dir / "tune.md"),
        }

        with open(day_dir / "tune.json", "w") as f:
            json.dump(tune, f, indent=2)

        (day_dir / "tune.md").write_text(markdown_narrative or raw_text)

        return tune


def _invalid_snapshot_reason(grade: dict) -> str | None:
    quality = grade.get("data_quality") or {}
    capture_valid = quality.get("capture_valid_for_opening_prediction")
    if capture_valid is None:
        capture_valid = grade.get("capture_valid_for_opening_prediction")

    capture_confidence = quality.get("capture_confidence")
    if capture_confidence is None:
        capture_confidence = grade.get("capture_confidence")

    capture_phase = quality.get("capture_phase")
    if capture_phase is None:
        capture_phase = grade.get("capture_phase")

    if capture_valid is False:
        return (
            "grade uses an invalid opening snapshot "
            f"(phase={capture_phase or 'unknown'}, confidence={capture_confidence or 'unknown'})"
        )

    if capture_confidence == "LOW":
        return f"grade uses a low-confidence opening snapshot (phase={capture_phase or 'unknown'})"

    if capture_phase in {"OPEN", "POST_OPEN", "OUT_OF_SESSION"}:
        return f"grade capture phase is not valid for tuning: {capture_phase}"

    return None


def _build_user_prompt(grade: dict) -> str:
    per_ticker_summary = []
    for t in grade.get("per_ticker", []):
        if t.get("no_track_data"):
            continue
        per_ticker_summary.append(
            f"  {t['ticker']:8s} "
            f"action={t.get('trade_setup_action') or '?':8s} "
            f"sig={t.get('signal_score', '?'):>3} "
            f"trend={t.get('trend', '?'):8s} "
            f"entry_hit={str(t.get('entry_range_hit', '?')):5s} "
            f"clean={str(t.get('clean_trade', '?')):5s} "
            f"iep_err={t.get('iep_error_pct', '?')}% "
            f"bp_preopen={t.get('bid_pressure_preopen', '?')} "
            f"bp_T0={t.get('bid_pressure_T0', '?')} "
            f"bp_T5={t.get('bid_pressure_T5', '?')} "
            f"bp_momentum={t.get('bid_momentum', '?')}"
        )

    config = grade.get("config_snapshot", {})
    by_action = grade.get("by_trade_setup_action", {})
    by_band = grade.get("by_signal_band", {})

    return f"""DATE: {grade.get("date")}

SESSION SUMMARY:
  Tickers screened: {grade.get("tickers_screened")} | Tracked: {grade.get("tickers_tracked")}
  Decision source: {grade.get("decision_source", "N/A")}
  Entry range hit rate:   {grade.get("entry_range_hit_rate", "N/A")}
  Trend accuracy T+5min:  {grade.get("trend_accuracy_T5", "N/A")}
  Trend accuracy T+15min: {grade.get("trend_accuracy_T15", "N/A")}
  Trend accuracy T+30min: {grade.get("trend_accuracy_T30", "N/A")}
  Clean trade rate:       {grade.get("clean_trade_rate", "N/A")}
  IEP mean error:         {grade.get("iep_accuracy", {}).get("mean_error_pct", "N/A")}%

BY TRADESETUP ACTION (champion):
  ENTER: count={by_action.get("ENTER", {}).get("count", 0)} clean_trade={
        by_action.get("ENTER", {}).get("clean_trade_rate", "N/A")
    } entry_hit={by_action.get("ENTER", {}).get("entry_range_hit_rate", "N/A")}
  WATCH: count={by_action.get("WATCH", {}).get("count", 0)} clean_trade={
        by_action.get("WATCH", {}).get("clean_trade_rate", "N/A")
    } entry_hit={by_action.get("WATCH", {}).get("entry_range_hit_rate", "N/A")}
  AVOID: count={by_action.get("AVOID", {}).get("count", 0)} clean_trade={
        by_action.get("AVOID", {}).get("clean_trade_rate", "N/A")
    }

BY SIGNAL BAND (champion):
  strong: count={by_band.get("strong", {}).get("count", 0)} clean_trade={
        by_band.get("strong", {}).get("clean_trade_rate", "N/A")
    }
  moderate: count={by_band.get("moderate", {}).get("count", 0)}
  clean_trade={by_band.get("moderate", {}).get("clean_trade_rate", "N/A")}
  weak: count={by_band.get("weak", {}).get("count", 0)} clean_trade={
        by_band.get("weak", {}).get("clean_trade_rate", "N/A")
    }

PER TICKER:
{chr(10).join(per_ticker_summary)}

CURRENT CONFIG:
  rsi_overbought_threshold:         {config.get("rsi_overbought_threshold", "N/A")}
  iev_intensity_unusual_threshold:  {config.get("iev_intensity_unusual_threshold", "N/A")}
  atr_range_cap_min:                {config.get("atr_range_cap_min", "N/A")}
  atr_range_cap_max:                {config.get("atr_range_cap_max", "N/A")}
  broker_backing_threshold:           {config.get("broker_backing_threshold", "N/A")}
  min_target_ticks:                 {config.get("min_target_ticks", "N/A")}
  tick_friction_gate:               {config.get("tick_friction_gate", "N/A")}

Analyze this and provide specific recommendations.
"""


def _call_deepseek(system_prompt: str, user_prompt: str, api_key: str | None) -> tuple[str, int]:
    """Call DeepSeek API directly with a higher token limit than the base explainer allows."""
    import os

    resolved_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not resolved_key:
        raise ValueError("No DeepSeek API key available")

    try:
        import openai
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    client = openai.OpenAI(
        api_key=resolved_key,
        base_url="https://api.deepseek.com",
        timeout=60,
        max_retries=1,
    )
    response = client.chat.completions.create(
        model="deepseek-chat",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    text = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else 0
    return text, tokens


def _parse_response(raw: str) -> tuple[dict, str]:
    """Extract JSON block and markdown narrative from DeepSeek response."""
    json_block: dict = {}
    narrative = raw

    # Find the ```json ... ``` block by locating the opening brace and using
    # a brace-counting approach rather than regex, to handle nested JSON.
    start_marker = raw.find("```json")
    if start_marker != -1:
        brace_start = raw.find("{", start_marker)
        if brace_start != -1:
            depth = 0
            i = brace_start
            while i < len(raw):
                if raw[i] == "{":
                    depth += 1
                elif raw[i] == "}":
                    depth -= 1
                    if depth == 0:
                        json_str = raw[brace_start : i + 1]
                        try:
                            json_block = json.loads(json_str)
                            # Narrative is everything after the closing ``` marker
                            end_marker = raw.find("```", i)
                            if end_marker != -1:
                                narrative = raw[end_marker + 3 :].strip()
                            else:
                                narrative = raw[i + 1 :].strip()
                        except json.JSONDecodeError:
                            pass
                        break
                i += 1

    if not narrative:
        narrative = raw

    return json_block, narrative


def _now_iso() -> str:
    from datetime import datetime

    from src.domain.value_objects.idx_market import IDX_TIMEZONE

    return datetime.now(IDX_TIMEZONE).isoformat()
