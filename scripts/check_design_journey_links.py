#!/usr/bin/env python3
"""Resolve relative hrefs from design hub HTML files under docs/design/.

Usage (repo root):
  python scripts/check_design_journey_links.py
  python scripts/check_design_journey_links.py --hub docs/design/tui-journey-hub.html

Exit 0 when all relative .html links from the hub (and optional peers) exist.
No network. Pure stdlib — design-only verification helper.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HREF_RE = re.compile(r"""href=["']([^"'#]+)["']""", re.I)

REQUIRED_HUB_LABELS = (
    "Judge",
    "Plan",
    "accum",
    "ticker",
    "broker",
    "pre-open",
    "paper",
    "Health",
    "Action path",
    "Browse path",
    "Paper path",
)

REQUIRED_FILES = (
    "tui-journey-hub.html",
    "tui-judge-desk.html",
    "tui-plan-desk.html",
    "tui-accum-board.html",
    "tui-ticker-desk.html",
    "tui-broker-desk.html",
    "tui-preopen-board.html",
    "tui-paper-journal.html",
    "tui-session-health.html",
    "tui-cockpit-opencode.html",
    "end-to-end-journey.html",
)


def collect_hrefs(html: str) -> list[str]:
    out: list[str] = []
    for m in HREF_RE.finditer(html):
        href = m.group(1).strip()
        if href.startswith(("http://", "https://", "mailto:", "data:", "javascript:")):
            continue
        if href.startswith("/"):
            continue  # absolute site paths not used in design mocks
        out.append(href)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--design-dir",
        type=Path,
        default=Path("docs/design"),
        help="Design directory (default: docs/design)",
    )
    parser.add_argument(
        "--hub",
        type=Path,
        default=None,
        help="Hub HTML path (default: <design-dir>/tui-journey-hub.html)",
    )
    args = parser.parse_args()
    design_dir = args.design_dir.resolve()
    hub = (args.hub or (args.design_dir / "tui-journey-hub.html")).resolve()

    errors: list[str] = []
    notes: list[str] = []

    if not design_dir.is_dir():
        print(f"FAIL: design dir missing: {design_dir}", file=sys.stderr)
        return 2

    for name in REQUIRED_FILES:
        path = design_dir / name
        if not path.is_file():
            errors.append(f"missing required file: {name}")
        elif path.stat().st_size < 500:
            errors.append(f"file too small (stub?): {name} ({path.stat().st_size} bytes)")
        else:
            notes.append(f"ok file {name} ({path.stat().st_size} bytes)")

    if not hub.is_file():
        errors.append(f"hub missing: {hub}")
        _print_report(notes, errors)
        return 1

    hub_text = hub.read_text(encoding="utf-8")
    for label in REQUIRED_HUB_LABELS:
        if label.lower() not in hub_text.lower():
            errors.append(f"hub missing label/term: {label!r}")

    # Surface signature greps
    surface_checks = {
        "tui-judge-desk.html": ("Verdict Mast", "WATCH", "Phase sequence"),
        "tui-plan-desk.html": ("Geometry Mast", "Entry", "Stop", "Target"),
        "tui-accum-board.html": ("Signal", "Action", "snapshot"),
        "tui-ticker-desk.html": ("Harga", "BBCA", "6,275"),
        "tui-broker-desk.html": ("Radar", "Net Mast", "YP"),
    }
    for fname, needles in surface_checks.items():
        text = (design_dir / fname).read_text(encoding="utf-8") if (design_dir / fname).is_file() else ""
        for n in needles:
            if n.lower() not in text.lower():
                errors.append(f"{fname} missing expected content: {n!r}")

    checked: set[Path] = set()
    for href in collect_hrefs(hub_text):
        # only check relative paths under design dir
        target = (hub.parent / href).resolve()
        checked.add(target)
        if not target.exists():
            errors.append(f"broken hub link: {href} -> {target}")
        else:
            notes.append(f"ok link {href}")

    # Also scan each required html for broken relative .html links within design/
    for name in REQUIRED_FILES:
        path = design_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for href in collect_hrefs(text):
            if not href.endswith(".html") and ".html" not in href:
                continue
            # strip query
            clean = href.split("?")[0]
            target = (path.parent / clean).resolve()
            try:
                target.relative_to(design_dir)
            except ValueError:
                continue  # outside design dir
            if not target.exists():
                errors.append(f"broken link in {name}: {href}")

    _print_report(notes, errors)
    return 1 if errors else 0


def _print_report(notes: list[str], errors: list[str]) -> None:
    print("=== design journey link check ===")
    print(f"notes={len(notes)} errors={len(errors)}")
    for e in errors:
        print(f"ERROR: {e}")
    if not errors:
        print("PASS: all required design files and hub links OK")


if __name__ == "__main__":
    raise SystemExit(main())
