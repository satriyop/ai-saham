"""Shared adapter composition/wiring reused by more than one UI adapter.

These modules build workflow dependencies and use-case bundles that both the CLI
and the TUI need. They live here — not inside any single UI adapter package — so
sibling adapters never import one another (hexagonal boundary): each UI adapter
depends inward on this shared composition, not sideways on a peer.

Layer: Adapter (composition / wiring only)
"""
