"""
SKILL.md generation trigger for the strategy validate CLI command.

Layer: Adapter
"""

from pathlib import Path

from src.adapters.cli.strategy_lifecycle_display import print_skill_generation_result
from src.adapters.cli.strategy_lifecycle_factory import create_skill_generator_service


def generate_skill_md_for_strategy(strategy_path: Path) -> None:
    """Generate SKILL.md after successful strategy validation.

    Silently skips if no sidecar .skill.yaml exists (3rd party strategy).
    Warns on drift detection or generation issues.

    Args:
        strategy_path: Path to the validated strategy.yaml.
    """
    strategy_dir = strategy_path.parent
    sidecar_path = strategy_dir / "strategy.skill.yaml"

    # Skip silently for strategies without sidecar annotations (3rd party)
    if not sidecar_path.exists():
        return

    generator = create_skill_generator_service()
    result = generator.generate_for_strategy(strategy_path)

    print_skill_generation_result(result)
