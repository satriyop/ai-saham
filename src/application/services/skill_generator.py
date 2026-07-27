"""
Skill generator service.

Orchestrates SKILL.md generation by combining annotation reading,
metadata auto-detection, and markdown rendering.

Layer: Application
"""

from dataclasses import dataclass
from pathlib import Path

from src.application.ports.annotation_reader import AnnotationReader
from src.application.ports.rules_hasher import RulesHasher
from src.application.ports.skill_writer import SkillWriter
from src.application.ports.strategy_document_reader import StrategyDocumentReader
from src.domain.value_objects.skill_annotation import (
    ArtifactType,
    DriftInfo,
    SkillAnnotation,
    SkillMetadata,
)

# Indicators that require broker flow data
_BROKER_INDICATORS = {"FOREIGN_FLOW", "FOREIGN_FLOW_RATIO", "CONSECUTIVE_FOREIGN_BUY"}


@dataclass(frozen=True)
class SkillGenerationResult:
    """Result of generating a SKILL.md file.

    Attributes:
        success: Whether generation completed without errors.
        output_path: Path to the generated SKILL.md (None on failure).
        warnings: Warning messages during generation.
        drift_detected: Whether the rules changed since last generation.
    """

    success: bool
    output_path: Path | None
    warnings: tuple[str, ...]
    drift_detected: bool


class SkillGeneratorService:
    """Orchestrates SKILL.md generation for all artifact types."""

    def __init__(
        self,
        annotation_reader: AnnotationReader,
        skill_writer: SkillWriter,
        rules_hasher: RulesHasher,
        strategy_reader: StrategyDocumentReader,
    ) -> None:
        self._reader = annotation_reader
        self._writer = skill_writer
        self._hasher = rules_hasher
        self._strategy_reader = strategy_reader

    def generate_for_strategy(self, strategy_path: Path) -> SkillGenerationResult:
        """Generate SKILL.md for a strategy.

        Args:
            strategy_path: Path to strategy.yaml.

        Returns:
            SkillGenerationResult with generation outcome.
        """
        warnings: list[str] = []

        # Load strategy YAML
        try:
            data = self._strategy_reader.read_strategy(strategy_path)
        except Exception as e:
            return SkillGenerationResult(
                success=False,
                output_path=None,
                warnings=(f"Could not load strategy: {e}",),
                drift_detected=False,
            )

        strategy_name = data.get("name", strategy_path.parent.name)
        strategy_dir = strategy_path.parent

        # Read sidecar annotation
        sidecar_path = strategy_dir / "strategy.skill.yaml"
        annotation = self._read_annotation_safe(sidecar_path, warnings)

        # Auto-detect dependencies from indicators section
        indicators_data = data.get("indicators", {})
        dependencies = self._extract_dependencies(indicators_data)

        # Auto-detect data requirements
        data_requirements = self._detect_data_requirements(indicators_data)

        # Parse rules into summaries
        rules_summary = self._extract_rules_summary(data.get("rules", []))

        # Derive CLI usage
        dir_name = strategy_dir.name
        cli_usage = (
            f"saham strategy validate {dir_name}",
            f"saham backtest BBCA --strategy {dir_name}",
        )

        # Compute drift
        skill_md_path = strategy_dir / "SKILL.md"
        drift = self._compute_drift(strategy_path, skill_md_path, warnings)

        # Assemble metadata
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name=strategy_name,
            artifact_path=strategy_path,
            annotation=annotation,
            cli_usage=cli_usage,
            dependencies=dependencies,
            data_requirements=data_requirements,
            rules_summary=rules_summary,
            drift=drift,
        )

        # Write SKILL.md
        try:
            self._writer.write_skill(metadata, skill_md_path)
        except Exception as e:
            return SkillGenerationResult(
                success=False,
                output_path=None,
                warnings=tuple(warnings) + (f"Could not write SKILL.md: {e}",),
                drift_detected=drift.is_stale if drift else False,
            )

        return SkillGenerationResult(
            success=True,
            output_path=skill_md_path,
            warnings=tuple(warnings),
            drift_detected=drift.is_stale if drift else False,
        )

    def generate_for_indicator(self, plugin_path: Path) -> SkillGenerationResult:
        """Generate SKILL.md for an indicator plugin.

        Args:
            plugin_path: Path to the indicator Python file.

        Returns:
            SkillGenerationResult with generation outcome.
        """
        warnings: list[str] = []

        indicator_name = plugin_path.stem
        plugin_dir = plugin_path.parent

        # Read sidecar annotation
        sidecar_path = plugin_dir / f"{indicator_name}.skill.yaml"
        annotation = self._read_annotation_safe(sidecar_path, warnings)

        cli_usage = (f"saham compute {indicator_name.upper()} BBCA",)

        metadata = SkillMetadata(
            artifact_type=ArtifactType.INDICATOR,
            artifact_name=indicator_name.upper(),
            artifact_path=plugin_path,
            annotation=annotation,
            cli_usage=cli_usage,
        )

        skill_md_path = plugin_dir / f"{indicator_name}.SKILL.md"
        try:
            self._writer.write_skill(metadata, skill_md_path)
        except Exception as e:
            return SkillGenerationResult(
                success=False,
                output_path=None,
                warnings=tuple(warnings) + (f"Could not write SKILL.md: {e}",),
                drift_detected=False,
            )

        return SkillGenerationResult(
            success=True,
            output_path=skill_md_path,
            warnings=tuple(warnings),
            drift_detected=False,
        )

    def generate_for_formula(
        self, formula_name: str, formulas_path: Path, *, output_dir: Path | None = None
    ) -> SkillGenerationResult:
        """Generate SKILL.md for a single formula.

        Args:
            formula_name: Name of the formula (e.g., "SMOOTH_RSI").
            formulas_path: Path to formulas.yaml.

        Returns:
            SkillGenerationResult with generation outcome.
        """
        warnings: list[str] = []

        # Read formula-keyed sidecar
        sidecar_path = formulas_path.parent / "formulas.skill.yaml"
        annotations = {}
        try:
            annotations = self._reader.read_formula_annotations(sidecar_path)
        except Exception as e:
            warnings.append(f"Could not read formula annotations: {e}")

        annotation = annotations.get(formula_name)
        if annotation is None:
            warnings.append(f"No annotation found for formula '{formula_name}' in {sidecar_path}")

        cli_usage = (f"saham compute {formula_name} BBCA",)

        metadata = SkillMetadata(
            artifact_type=ArtifactType.FORMULA,
            artifact_name=formula_name,
            artifact_path=formulas_path,
            annotation=annotation,
            cli_usage=cli_usage,
        )

        # Write to skills/formulas/ directory
        skills_dir = output_dir if output_dir is not None else Path("skills/formulas")
        skill_md_path = skills_dir / f"{formula_name}.SKILL.md"

        try:
            self._writer.write_skill(metadata, skill_md_path)
        except Exception as e:
            return SkillGenerationResult(
                success=False,
                output_path=None,
                warnings=tuple(warnings) + (f"Could not write SKILL.md: {e}",),
                drift_detected=False,
            )

        return SkillGenerationResult(
            success=True,
            output_path=skill_md_path,
            warnings=tuple(warnings),
            drift_detected=False,
        )

    # ── Private helpers ─────────────────────────────────────────────

    def _read_annotation_safe(
        self, sidecar_path: Path, warnings: list[str]
    ) -> SkillAnnotation | None:
        """Read annotation, appending warnings on failure."""
        try:
            annotation = self._reader.read(sidecar_path)
            if annotation is None:
                warnings.append(f"No sidecar found at {sidecar_path}")
            return annotation
        except Exception as e:
            warnings.append(f"Invalid sidecar {sidecar_path}: {e}")
            return None

    def _extract_dependencies(self, indicators_data: dict) -> tuple[str, ...]:
        """Extract indicator type names from the indicators section."""
        if not indicators_data:
            return ()

        deps: list[str] = []
        for _alias, config in indicators_data.items():
            if isinstance(config, dict):
                indicator_type = config.get("type", "")
                if indicator_type and indicator_type not in deps:
                    deps.append(indicator_type)

        return tuple(sorted(deps))

    def _detect_data_requirements(self, indicators_data: dict) -> tuple[str, ...]:
        """Detect data sources required by the strategy's indicators."""
        requirements: set[str] = {"ohlcv"}  # All strategies need price data

        if not indicators_data:
            return tuple(sorted(requirements))

        for _alias, config in indicators_data.items():
            if isinstance(config, dict):
                indicator_type = config.get("type", "").upper()
                if indicator_type in _BROKER_INDICATORS:
                    requirements.add("broker_flow")

        return tuple(sorted(requirements))

    def _extract_rules_summary(self, rules: list) -> tuple[str, ...]:
        """Extract brief summary strings from rules."""
        summaries: list[str] = []
        for rule in rules:
            if isinstance(rule, dict):
                name = rule.get("name", "unnamed")
                rationale = rule.get("rationale", "")
                outcome = rule.get("outcome", "")
                if rationale:
                    summary = f"**{name}** ({outcome}): {rationale}"
                else:
                    summary = f"**{name}** ({outcome})"
                summaries.append(summary)
        return tuple(summaries)

    def _compute_drift(
        self,
        strategy_path: Path,
        skill_md_path: Path,
        warnings: list[str],
    ) -> DriftInfo:
        """Compute drift info for a strategy."""
        try:
            current_hash = self._hasher.compute_hash(strategy_path)
            stored_hash = self._hasher.extract_stored_hash(skill_md_path)
            is_stale = stored_hash is not None and current_hash != stored_hash

            if is_stale:
                warnings.append("SKILL.md is stale — rules have changed since last generation")

            return DriftInfo(
                rules_hash=current_hash,
                is_stale=is_stale,
                stored_hash=stored_hash,
            )
        except Exception as e:
            warnings.append(f"Could not compute drift: {e}")
            return DriftInfo(
                rules_hash="",
                is_stale=False,
                stored_hash=None,
            )
