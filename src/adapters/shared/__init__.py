"""Adapter-neutral presentation helpers shared across CLI, TUI, bot, and web.

Modules here must stay free of adapter-framework dependencies (typer, rich,
textual, …) so any adapter can import them without one adapter reaching into
another. Framework-specific rendering stays in the owning adapter.

Layer: Adapter (shared)
"""
