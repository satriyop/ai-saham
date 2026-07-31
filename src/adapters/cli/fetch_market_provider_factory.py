"""Broker provider construction — re-export from shared composition.

Kept under adapters.cli for existing import paths; implementation lives in
adapters.composition so TUI/shared factories never import the CLI package.

Layer: Adapter
"""

from src.adapters.composition.broker_provider_factory import create_broker_provider

__all__ = ["create_broker_provider"]
