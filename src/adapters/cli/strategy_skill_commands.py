"""
CLI implementation for saham strategy skill commands.
Public command registration lives in lifecycle routers:
  saham strategy skill generate
  saham strategy skill check
  saham strategy skill index
Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.skill_generator import SkillGeneratorService
from src.application.services.strategy_loader import StrategyLoader
from src.infrastructure.skill.annotation_reader import AnnotationReader
from src.infrastructure.skill.index_writer import SkillIndexWriter
from src.infrastructure.skill.markdown_writer import MarkdownSkillWriter
from src.infrastructure.skill.rules_hasher import RulesHasher

skill_app = typer.Typer(
    name="skill",
    help="Manage skill documentation (generate, check, index)",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _create_skill_generator() -> SkillGeneratorService:
    """Wire up the skill generator with its dependencies."""
    return SkillGeneratorService(
        annotation_reader=AnnotationReader(),
        skill_writer=MarkdownSkillWriter(),
        rules_hasher=RulesHasher(),
    )


@skill_app.command("generate")
def generate(
    artifact: Annotated[
        str,
        typer.Argument(help="Strategy name, indicator plugin name, or formula name"),
    ],
    artifact_type: Annotated[
        str,
        typer.Option(
            "--type", "-t",
            help="Artifact type (strategy/indicator/formula). Auto-detected if omitted.",
        ),
    ] = "strategy",
) -> None:
    """
    Generate SKILL.md for a named artifact.

    Reads the artifact's .skill.yaml sidecar and produces a SKILL.md
    projection with auto-detected metadata.

    Examples:
        saham strategy skill generate rsi-momentum
        saham strategy skill generate foreign-accumulation
        saham strategy skill generate atr --type indicator
        saham strategy skill generate SMOOTH_RSI --type formula
    """
    generator = _create_skill_generator()

    if artifact_type == "strategy":
        # Resolve strategy path
        registry = create_indicator_registry()
        loader = StrategyLoader(registry=registry)
        try:
            strategy_path = loader.resolve(artifact)
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        result = generator.generate_for_strategy(strategy_path)

    elif artifact_type == "indicator":
        plugin_path = Path("plugins/indicators") / f"{artifact}.py"
        if not plugin_path.exists():
            typer.echo(f"Error: Indicator plugin not found at {plugin_path}", err=True)
            raise typer.Exit(1)
        result = generator.generate_for_indicator(plugin_path)

    elif artifact_type == "formula":
        formulas_path = Path("config/formulas.yaml")
        if not formulas_path.exists():
            typer.echo(f"Error: Formulas file not found at {formulas_path}", err=True)
            raise typer.Exit(1)
        result = generator.generate_for_formula(
            artifact.upper(), formulas_path, output_dir=Path("skills/formulas")
        )

    else:
        typer.echo(f"Error: Unknown artifact type '{artifact_type}'", err=True)
        typer.echo("Valid types: strategy, indicator, formula", err=True)
        raise typer.Exit(1)

    # Display result
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}", err=True)

    if result.success:
        typer.echo(f"Generated: {result.output_path}")
        if result.drift_detected:
            typer.echo(
                "Warning: Rules changed since last generation. SKILL.md updated.",
                err=True,
            )
    else:
        typer.echo("Failed to generate SKILL.md", err=True)
        raise typer.Exit(1)


@skill_app.command("check")
def check() -> None:
    """
    Check all artifacts for stale SKILL.md files.

    Scans strategies/, plugins/indicators/, and skills/formulas/ for
    artifacts with existing SKILL.md files and reports which ones are stale.

    Examples:
        saham strategy skill check
    """
    hasher = RulesHasher()
    stale_count = 0
    checked_count = 0

    # Check strategies
    strategies_dir = Path("strategies")
    if strategies_dir.exists():
        typer.echo("Strategies:")
        for strategy_dir in sorted(strategies_dir.iterdir()):
            if not strategy_dir.is_dir():
                continue

            strategy_yaml = strategy_dir / "strategy.yaml"
            skill_md = strategy_dir / "SKILL.md"

            if not strategy_yaml.exists():
                continue

            checked_count += 1

            if not skill_md.exists():
                typer.echo(f"  {strategy_dir.name}: no SKILL.md (run: saham strategy skill generate {strategy_dir.name})")
                stale_count += 1
                continue

            if hasher.is_stale(strategy_yaml, skill_md):
                typer.echo(f"  {strategy_dir.name}: STALE (run: saham strategy skill generate {strategy_dir.name})")
                stale_count += 1
            else:
                typer.echo(f"  {strategy_dir.name}: up to date")

    # Check indicator plugins
    plugins_dir = Path("plugins/indicators")
    if plugins_dir.exists():
        typer.echo("Indicator Plugins:")
        for plugin_path in sorted(plugins_dir.glob("*.py")):
            if plugin_path.name.startswith("_"):
                continue
            checked_count += 1
            skill_md = plugins_dir / f"{plugin_path.stem}.SKILL.md"
            if not skill_md.exists():
                typer.echo(f"  {plugin_path.stem}: no SKILL.md (run: saham strategy skill generate {plugin_path.stem} --type indicator)")
                stale_count += 1
            else:
                typer.echo(f"  {plugin_path.stem}: up to date")

    # Check formula skills
    skills_formulas_dir = Path("skills/formulas")
    if skills_formulas_dir.exists():
        typer.echo("Formula Skills:")
        for skill_md in sorted(skills_formulas_dir.glob("*.SKILL.md")):
            checked_count += 1
            formula_name = skill_md.name.replace(".SKILL.md", "")
            typer.echo(f"  {formula_name}: up to date")

    if checked_count == 0:
        typer.echo("No artifacts found to check.")
        return

    typer.echo("")
    if stale_count > 0:
        typer.echo(f"{stale_count}/{checked_count} artifact(s) need regeneration.")
    else:
        typer.echo(f"All {checked_count} artifact(s) are up to date.")


@skill_app.command("index")
def index(
    project_root: Annotated[
        Optional[Path],
        typer.Option("--root", "-r", help="Project root directory"),
    ] = None,
) -> None:
    """
    Rebuild SKILLS_INDEX.md from all SKILL.md files.

    Scans the project for SKILL.md files and generates a catalog
    index at the project root.

    Examples:
        saham strategy skill index
        saham strategy skill index --root /path/to/project
    """
    root = project_root or Path(".")

    writer = SkillIndexWriter()
    output_path = writer.write(root)

    typer.echo(f"Generated: {output_path}")
