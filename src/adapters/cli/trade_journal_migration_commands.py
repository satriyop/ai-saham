"""
CLI command for one-time CSV-to-JSONL journal migration.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_accum_commands import DEFAULT_ACCUM_JOURNAL_PATH
from src.adapters.cli.trade_intraday_commands import DEFAULT_CONFIRMATION_JOURNAL_PATH
from src.infrastructure.config.app_config import APP_CFG


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
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )
    from src.infrastructure.persistence.trade_journal_jsonl_writer import (
        TradeJournalJsonlWriter,
        accumulation_entry_to_record,
        intraday_entry_to_record,
    )

    output_path = trades_journal or Path(APP_CFG.storage.trade_journal)
    accum_path = accum_csv or DEFAULT_ACCUM_JOURNAL_PATH
    intraday_path = intraday_csv or DEFAULT_CONFIRMATION_JOURNAL_PATH

    swing_entries = (
        AccumulationJournalCsvWriter(accum_path).read_all()
        if accum_path.exists()
        else []
    )
    intraday_entries = (
        IntradayConfirmationCsvStore(intraday_path).read_all()
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
