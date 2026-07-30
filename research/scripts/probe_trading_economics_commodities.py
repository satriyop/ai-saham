#!/usr/bin/env python3
"""
Probe-only: Trading Economics commodity pages (palm oil, coal, …).

Research / DQ investigation — NOT a MarketDataProvider and NOT wired into
`src/`, CLI, or fetch market.

What this does:
  1. GET public TE commodity HTML pages
  2. Parse TEChartsMeta snapshot (last price, ticker, chart flags)
  3. Parse meta description / JSON-LD (units, CFD language)
  4. Probe CloudFront chart host for plain JSON history
  5. Compare last levels to local Yahoo candles (CPO=F, COAL) when data.db exists
  6. Write a markdown + JSON artifact under research/artifacts/

What this does NOT do:
  - Persist into candles / macro tables
  - Decrypt TE obfuscated chart payloads (anti-scrape layer)
  - Recommend production scrape wiring (ToS + fragility)

Usage:
  python research/scripts/probe_trading_economics_commodities.py
  python research/scripts/probe_trading_economics_commodities.py --db data/db/data.db

Exit 0 even when history is obfuscated (probe always completes; report is the product).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Constants — probe targets only
# --------------------------------------------------------------------------- #

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_TARGETS: tuple[dict[str, str], ...] = (
    {
        "id": "palm_oil",
        "url": "https://tradingeconomics.com/commodity/palm-oil",
        "yahoo_compare": "CPO=F",
        "note": "Plantation SMC driver candidate vs thin Yahoo CPO=F",
    },
    {
        "id": "coal",
        "url": "https://tradingeconomics.com/commodity/coal",
        "yahoo_compare": "COAL",
        "note": "Coal SMC driver candidate vs COAL ETF proxy",
    },
)

CHART_HOST = "https://d3ii0wo49og5mi.cloudfront.net"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "research" / "artifacts"
DEFAULT_DB = REPO_ROOT / "data" / "db" / "data.db"


# --------------------------------------------------------------------------- #
# HTTP + parse helpers
# --------------------------------------------------------------------------- #


def _http_get(
    url: str,
    *,
    accept: str = "text/html,*/*",
    timeout: float = 25.0,
) -> tuple[int, str, bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://tradingeconomics.com/",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), str(resp.headers.get("Content-Type") or ""), resp.read()


def _parse_ms_date(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        m = re.search(r"/Date\((-?\d+)\)/", raw)
        if m:
            ts = int(m.group(1)) / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        # already iso-ish
        if re.match(r"\d{4}-\d{2}-\d{2}", raw):
            return raw[:10]
    return str(raw)


def _extract_te_charts_meta(html: str) -> dict[str, Any] | None:
    """Return the richest TEChartsMeta JSON object (snapshot, not full series)."""
    best: dict[str, Any] | None = None
    best_score = -1
    for m in re.finditer(r"TEChartsMeta\s*=\s*", html):
        i = m.end()
        if i >= len(html) or html[i] != "[":
            continue
        depth = 0
        j = i
        in_str = False
        esc = False
        while j < len(html):
            ch = html[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
            j += 1
        raw = html[i:j]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            continue
        obj = data[0]
        score = len(obj)
        if score > best_score:
            best = obj
            best_score = score
    return best


def _extract_meta_description(html: str) -> str | None:
    m = re.search(
        r'<meta[^>]+id="metaDesc"[^>]+content="([^"]+)"',
        html,
        flags=re.I,
    ) or re.search(
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
        html,
        flags=re.I,
    )
    if not m:
        return None
    return unescape(m.group(1)).replace("&#39;", "'")


def _extract_json_ld_datasets(html: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in re.finditer(
        r'<script type="application/ld\+json">(.*?)</script>',
        html,
        flags=re.I | re.S,
    ):
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("@type") == "Dataset":
            out.append(payload)
        if isinstance(payload, dict) and isinstance(payload.get("@graph"), list):
            for node in payload["@graph"]:
                if isinstance(node, dict) and node.get("@type") == "Dataset":
                    out.append(node)
    return out


def _extract_js_assignments(html: str) -> dict[str, str]:
    """Last non-empty TESymbol / TEChartsDatasource / token from page scripts."""
    found: dict[str, str] = {}
    for key in ("TESymbol", "TEChartsDatasource", "TEChartsToken", "TEChartUrl", "TEType"):
        matches = re.findall(rf"var {key}\s*=\s*'([^']*)'", html)
        # prefer last non-empty
        for val in matches:
            if val:
                found[key] = val
        if key not in found and matches:
            found[key] = matches[-1]
    return found


def _looks_obfuscated_payload(body: bytes) -> bool:
    if not body:
        return False
    text = body[:80].decode("utf-8", "replace").strip()
    # TE chart payloads often start with a quoted ciphertext blob
    if text.startswith('"') and "series" not in text[:200].lower():
        return True
    try:
        json.loads(body)
        return False
    except json.JSONDecodeError:
        return True


def _yahoo_last_close(db_path: Path, ticker: str) -> dict[str, Any] | None:
    if not db_path.is_file():
        return None
    try:
        con = sqlite3.connect(str(db_path))
        row = con.execute(
            """
            SELECT date, close, volume, source
            FROM candles
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (ticker,),
        ).fetchone()
        # zero-vol density last 30
        z = con.execute(
            """
            SELECT COUNT(*), SUM(CASE WHEN volume IS NULL OR volume = 0 THEN 1 ELSE 0 END)
            FROM (
              SELECT volume FROM candles WHERE ticker = ? ORDER BY date DESC LIMIT 30
            )
            """,
            (ticker,),
        ).fetchone()
        con.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    n30, zero30 = z or (0, 0)
    return {
        "ticker": ticker,
        "date": row[0],
        "close": float(row[1]) if row[1] is not None else None,
        "volume": row[2],
        "source": row[3],
        "zero_vol_last_30": int(zero30 or 0),
        "n_last_30": int(n30 or 0),
    }


# --------------------------------------------------------------------------- #
# Probe models
# --------------------------------------------------------------------------- #


@dataclass
class ChartHostProbe:
    path: str
    url: str
    ok: bool
    status: int | None = None
    content_type: str | None = None
    nbytes: int = 0
    obfuscated: bool | None = None
    error: str | None = None


@dataclass
class CommodityProbeResult:
    id: str
    url: str
    note: str
    http_ok: bool
    http_status: int | None = None
    error: str | None = None
    page_title: str | None = None
    meta_description: str | None = None
    te_symbol: str | None = None
    charts_meta: dict[str, Any] = field(default_factory=dict)
    json_ld: list[dict[str, Any]] = field(default_factory=list)
    chart_host_probes: list[ChartHostProbe] = field(default_factory=list)
    yahoo_compare: dict[str, Any] | None = None
    findings: list[str] = field(default_factory=list)


def probe_commodity(target: dict[str, str], *, db_path: Path | None) -> CommodityProbeResult:
    result = CommodityProbeResult(
        id=target["id"],
        url=target["url"],
        note=target.get("note") or "",
        http_ok=False,
    )
    try:
        status, _ct, body = _http_get(target["url"])
        html = body.decode("utf-8", "replace")
        result.http_ok = True
        result.http_status = status
    except urllib.error.HTTPError as e:
        result.error = f"HTTPError {e.code}: {e.reason}"
        result.http_status = e.code
        return result
    except Exception as e:  # noqa: BLE001 — probe must never crash the batch
        result.error = f"{type(e).__name__}: {e}"
        return result

    title_m = re.search(r"<title>\s*(.*?)\s*</title>", html, flags=re.I | re.S)
    result.page_title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else None
    result.meta_description = _extract_meta_description(html)
    js_vars = _extract_js_assignments(html)
    result.te_symbol = js_vars.get("TESymbol")

    meta = _extract_te_charts_meta(html)
    if meta:
        # Normalize for report
        result.charts_meta = {
            "name": meta.get("name"),
            "full_name": meta.get("full_name"),
            "ticker": meta.get("ticker") or meta.get("symbol"),
            "symbol": meta.get("symbol"),
            "value": meta.get("value"),
            "last": meta.get("last"),
            "type": meta.get("type"),
            "first_date": _parse_ms_date(meta.get("first_date")),
            "has_daily": meta.get("has_daily"),
            "has_intraday": meta.get("has_intraday"),
            "has_no_volume": meta.get("has_no_volume"),
            "has_weekly_and_monthly": meta.get("has_weekly_and_monthly"),
            "timezone": meta.get("timezone"),
            "default_interval": meta.get("default_interval"),
            "allowed_interval": meta.get("allowed_interval"),
            "chart_type": meta.get("chart_type"),
        }
        result.findings.append(
            f"HTML snapshot last={result.charts_meta.get('value')} "
            f"ticker={result.charts_meta.get('ticker')}"
        )
    else:
        result.findings.append("TEChartsMeta snapshot not found (layout change?)")

    for ds in _extract_json_ld_datasets(html):
        slim = {
            "name": ds.get("name"),
            "alternateName": ds.get("alternateName"),
            "description": (ds.get("description") or "")[:400],
        }
        result.json_ld.append(slim)
        desc = (ds.get("description") or "").lower()
        if "cfd" in desc:
            result.findings.append(
                "JSON-LD describes series as CFD-linked (not exchange floor OHLC)"
            )

    if result.meta_description:
        d = result.meta_description.lower()
        if "myr" in d:
            result.findings.append("Meta description quotes MYR units (palm)")
        if "usd" in d and "coal" in result.id:
            result.findings.append("Meta description quotes USD units (coal)")

    # CloudFront chart host — history is typically obfuscated
    tickers_to_try: list[str] = []
    if result.charts_meta.get("ticker"):
        tickers_to_try.append(str(result.charts_meta["ticker"]))
    if result.te_symbol:
        tickers_to_try.append(result.te_symbol)
        tickers_to_try.append(result.te_symbol.upper())
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tickers_to_try:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)

    paths: list[str] = []
    for t in uniq:
        paths.extend(
            [
                f"/markets/{t}",
                f"/markets/{urllib.parse.quote(t, safe='')}",
                f"/markets/{t}?ohlc=1",
                f"/meta?s={urllib.parse.quote(t, safe='')}",
            ]
        )
    # unique paths
    path_seen: set[str] = set()
    for path in paths:
        if path in path_seen:
            continue
        path_seen.add(path)
        url = CHART_HOST + path
        probe = ChartHostProbe(path=path, url=url, ok=False)
        try:
            st, ct, body = _http_get(url, accept="application/json,*/*")
            probe.ok = True
            probe.status = st
            probe.content_type = ct
            probe.nbytes = len(body)
            probe.obfuscated = _looks_obfuscated_payload(body)
            if probe.obfuscated:
                result.findings.append(
                    f"Chart host {path}: HTTP {st}, obfuscated ({probe.nbytes} B)"
                )
            else:
                result.findings.append(
                    f"Chart host {path}: plain JSON ({probe.nbytes} B) — inspect artifact"
                )
        except urllib.error.HTTPError as e:
            probe.status = e.code
            probe.error = f"{e.code} {e.reason}"
        except Exception as e:  # noqa: BLE001
            probe.error = f"{type(e).__name__}: {e}"
        result.chart_host_probes.append(probe)

    ysym = target.get("yahoo_compare")
    if ysym and db_path is not None:
        result.yahoo_compare = _yahoo_last_close(db_path, ysym)
        if result.yahoo_compare and result.charts_meta.get("value") is not None:
            y = result.yahoo_compare.get("close")
            t = result.charts_meta.get("value")
            if y and t and y > 0:
                # levels are often different units — report ratio, not "match"
                result.findings.append(
                    f"Level check: TE last={t} vs Yahoo {ysym} close={y} "
                    f"(ratio TE/Yahoo={float(t) / float(y):.4f}); units may differ"
                )

    # Product recommendation line
    has_snapshot = result.charts_meta.get("value") is not None
    history_plain = any(p.ok and p.obfuscated is False for p in result.chart_host_probes)
    if has_snapshot and not history_plain:
        result.findings.append(
            "VERDICT: free HTML gives last price + metadata only; full history not plain JSON"
        )
    elif history_plain:
        result.findings.append("VERDICT: plain history found — re-evaluate before any product use")
    else:
        result.findings.append("VERDICT: insufficient free data for SMC candle backfill")

    return result


def _write_artifacts(results: list[CommodityProbeResult], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    json_path = out_dir / f"te_commodity_probe_{stamp}.json"
    md_path = out_dir / f"te_commodity_probe_{stamp}.md"

    payload = {
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "research probe only — not production",
        "chart_host": CHART_HOST,
        "results": [asdict(r) for r in results],
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    lines: list[str] = [
        f"# Trading Economics commodity probe ({stamp})",
        "",
        "**Scope:** research only — zero decision authority; no `src/` wiring.",
        "",
        "## Summary",
        "",
        "Public TE commodity pages expose a **last-price snapshot** (`TEChartsMeta`) "
        "and marketing/JSON-LD text (often CFD language). Chart history is served from "
        f"`{CHART_HOST}` as **obfuscated** payloads (not plain OHLCV JSON). "
        "Guest Trading Economics REST API paths return **410 Gone**.",
        "",
        "Implication for sector-macro: scrape TE is **not** a free drop-in replacement "
        "for daily Yahoo candles (`CPO=F`, `COAL`). At best: last-print sanity check.",
        "",
    ]
    for r in results:
        lines.append(f"## {r.id}")
        lines.append("")
        lines.append(f"- URL: {r.url}")
        lines.append(f"- Note: {r.note}")
        http_label = f"OK {r.http_status}" if r.http_ok else "FAIL"
        lines.append(f"- HTTP: {http_label} {r.error or ''}".rstrip())
        if r.page_title:
            lines.append(f"- Title: {r.page_title}")
        if r.meta_description:
            lines.append(f"- Description: {r.meta_description[:240]}")
        if r.charts_meta:
            lines.append(f"- TEChartsMeta: `{json.dumps(r.charts_meta, default=str)}`")
        if r.yahoo_compare:
            lines.append(f"- Yahoo local: `{json.dumps(r.yahoo_compare, default=str)}`")
        lines.append("- Chart host probes:")
        for p in r.chart_host_probes:
            lines.append(
                f"  - `{p.path}` status={p.status} ok={p.ok} "
                f"obfuscated={p.obfuscated} nbytes={p.nbytes} err={p.error}"
            )
        lines.append("- Findings:")
        for f in r.findings:
            lines.append(f"  - {f}")
        lines.append("")

    lines.extend(
        [
            "## Product guidance",
            "",
            "1. Do **not** wire TE HTML scrape into `MarketDataProvider` without a paid API / ADR.",
            "2. Keep Yahoo `CPO=F` / `COAL` as DIAGNOSTIC proxies with documented limits.",
            "3. Optional: use this probe periodically to compare **last print** levels only.",
            "4. Full daily history requires TE paid API or another licensed commodity feed.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="SQLite path for Yahoo candle comparison (optional)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help="Artifact directory (default research/artifacts)",
    )
    parser.add_argument(
        "--no-yahoo",
        action="store_true",
        help="Skip local Yahoo candle comparison",
    )
    args = parser.parse_args(argv)

    db_path: Path | None = None if args.no_yahoo else args.db
    results = [probe_commodity(t, db_path=db_path) for t in DEFAULT_TARGETS]
    json_path, md_path = _write_artifacts(results, args.out_dir)

    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    for r in results:
        status = "OK" if r.http_ok else "FAIL"
        last = (r.charts_meta or {}).get("value")
        print(f"  [{status}] {r.id}: last={last} findings={len(r.findings)}")
        for f in r.findings[:4]:
            print(f"    - {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
