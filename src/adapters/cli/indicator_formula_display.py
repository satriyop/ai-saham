"""
Display helpers for formula list rendering.

Layer: Adapter
"""

from rich.console import Console
from rich.table import Table


def print_formula_list(registry, stored_formulas, show_formulas, resolved_path):
    from src.application.services.indicator_registry import BUILTIN_NAMES

    console = Console()

    console.print("")
    console.print("[bold]Built-in Indicators[/bold]")
    builtin_descriptions = {
        "SMA": "Simple Moving Average",
        "EMA": "Exponential Moving Average",
        "RSI": "Relative Strength Index",
    }

    builtin_table = Table(show_header=True, header_style="bold magenta")
    builtin_table.add_column("Indicator", style="cyan")
    builtin_table.add_column("Description", style="white")
    builtin_table.add_column("Default Period", justify="right")

    for ind_name in sorted(BUILTIN_NAMES):
        desc = builtin_descriptions.get(ind_name, "")
        period = registry.get_default_period(ind_name)
        builtin_table.add_row(ind_name, desc, str(period))
    console.print(builtin_table)

    plugin_names = (
        set(registry.list_indicators())
        - BUILTIN_NAMES
        - set(registry.list_formulas())
    )
    if plugin_names:
        console.print("")
        console.print("[bold]Plugin Indicators[/bold]")
        plugin_table = Table(show_header=True, header_style="bold magenta")
        plugin_table.add_column("Indicator", style="cyan")
        plugin_table.add_column("Default Period", justify="right")
        for ind_name in sorted(plugin_names):
            period = registry.get_default_period(ind_name)
            plugin_table.add_row(ind_name, str(period))
        console.print(plugin_table)

    console.print("")
    console.print("[bold]Custom Formulas[/bold]")
    if stored_formulas:
        custom_table = Table(show_header=True, header_style="bold magenta")
        custom_table.add_column("Indicator", style="cyan")
        if show_formulas:
            custom_table.add_column("Formula Expression", style="green")

        for ind_name, stored in sorted(stored_formulas.items()):
            if show_formulas:
                custom_table.add_row(ind_name, stored.formula)
            else:
                custom_table.add_row(ind_name)
        console.print(custom_table)
        console.print(f"Formulas file: {resolved_path}")
    else:
        console.print("No custom formulas saved.")
        console.print("Tip: Use `saham indicator create` to create custom indicators.")

    total = len(registry.list_indicators()) + len(stored_formulas)
    console.print(f"\nTotal available: {total}")
