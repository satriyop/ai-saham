#!/usr/bin/env python3
"""RETIRED (ADR-062): accumulation group-breadth score bonus factor card.

This script is intentionally non-executable as an active research feeder.
The conglomerate-group Accum score bonus is retired from production policy.
Historical generated markdown under research/artifacts/ remains non-authoritative.

For sector-context peer-return breadth (a different DIAG contract), inspect
fingerprint field `sc_sector_breadth` via production observation tools — do not
revive this Accum bonus card.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "RETIRED by ADR-062: factor_card_sector_breadth is not an active feeder.\n"
        "The Accum group-breadth score bonus is removed from production policy.\n"
        "Do not use this script as a production or challenge baseline.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
