"""Composition root for market-data fetch/refresh workflow wiring.

Relocated out of the CLI adapter so both the CLI and TUI composition roots can
build the fetch-market workflow without an adapter->adapter dependency.

Layer: Infrastructure composition
"""
