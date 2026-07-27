"""
CLI command for one-time CSV-to-JSONL journal migration.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.infrastructure.config.app_config import load_app_config


def trade_migrate_journal(
    trades_journal: Annotated[
        Optional[Path],
        typer.Option("--output", help="Output trades.jsonl path"),
    ] = None,
    accum_csv: Annotated[
        Optional[Path],
        typer.Option("--accum-csv", help="Source accumulation CSV"),
    ] = None,
    intraday_csv: Annotated[
        Optional[Path],
        typer.Option("--intraday-csv", help="Source intraday confirmations CSV"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print records without writing"),
    ] = False,
) -> None:
    """
    One-time migration: convert existing CSV journals to journals/trades.jsonl.

    Reads journals/accumulation.csv and journals/intraday-confirmations.csv,
    converts each row to the unified schema, and appends to trades.jsonl.
    Idempotent — safe to run multiple times.
    """
    from src.infrastructure.persistence.accumulation_journal_csv_writer import (
        AccumulationJournalCsvWriter,
    )
    from src.infrastructure.persistence.pre_open_paper_journal_csv import (
        PreOpenPaperJournalCsvStore,
    )
    from src.infrastructure.persistence.trade_journal_jsonl_writer import (
        TradeJournalJsonlWriter,
        accumulation_entry_to_record,
        intraday_entry_to_record,
    )

    cfg = load_app_config()
    output_path = trades_journal or Path(cfg.storage.trade_journal)
    accum_path = accum_csv or Path(cfg.storage.accum_journal)
    intraday_path = intraday_csv or Path(cfg.storage.pre_open_paper_journal)

    swing_entries = (
        AccumulationJournalCsvWriter(accum_path).read_all()
        if accum_path.exists()
        else []
    )
    intraday_entries = (
        PreOpenPaperJournalCsvStore(intraday_path).read_all()
        if intraday_path.exists()
        else []
    )

    records = [accumulation_entry_to_record(e) for e in swing_entries] + \
              [intraday_entry_to_record(e) for e in intraday_entries]

    if dry_run:
        import json
        for r in records:
            typer.echo(json.dumps(r))
        typer.echo(f"\n{len(records)} record(s) would be written to {output_path}")
        return

    store = TradeJournalJsonlWriter(output_path)
    written = sum(1 for r in records if store.append(r))
    skipped = len(records) - written
    typer.echo(
        f"Migration complete → {output_path}\n"
        f"  Swing:    {len(swing_entries)} source rows\n"
        f"  Intraday: {len(intraday_entries)} source rows\n"
        f"  Written:  {written}  Skipped (duplicates): {skipped}"
    )
