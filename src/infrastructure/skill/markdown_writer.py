"""
Markdown SKILL.md writer.

Generates SKILL.md content from SkillMetadata and writes to disk.

Layer: Infrastructure
"""

from pathlib import Path

from src.application.ports.skill_writer import SkillWriter
from src.domain.value_objects.skill_annotation import (
    ArtifactType,
    SkillMetadata,
)


class MarkdownSkillWriter(SkillWriter):
    """Renders SkillMetadata into markdown SKILL.md files."""

    def render_skill(self, metadata: SkillMetadata) -> str:
        """Render a SKILL.md content string from metadata.

        Args:
            metadata: Complete skill metadata for the artifact.

        Returns:
            Rendered markdown content.
        """
        parts: list[str] = []

        # Heading
        parts.append(f"# {metadata.artifact_name}\n")
        parts.append(f"**Type:** {metadata.artifact_type.value}\n")

        # Description
        if metadata.annotation:
            parts.append("## Description\n")
            parts.append(f"{metadata.annotation.description}\n")
        else:
            parts.append("## Description\n")
            parts.append("<!-- TODO: Add description in strategy.skill.yaml -->\n")

        # When to use
        if metadata.annotation:
            parts.append("## When to Use\n")
            parts.append(f"{metadata.annotation.when_to_use}\n")
        else:
            parts.append("## When to Use\n")
            parts.append("<!-- TODO: Add when_to_use in strategy.skill.yaml -->\n")

        # Tags
        if metadata.annotation and metadata.annotation.tags:
            parts.append("## Tags\n")
            tag_str = ", ".join(f"`{tag}`" for tag in metadata.annotation.tags)
            parts.append(f"{tag_str}\n")

        # CLI Usage
        if metadata.cli_usage:
            parts.append("## CLI Usage\n")
            parts.append("```bash")
            for usage in metadata.cli_usage:
                parts.append(usage)
            parts.append("```\n")

        # Dependencies
        if metadata.dependencies:
            parts.append("## Dependencies\n")
            for dep in metadata.dependencies:
                parts.append(f"- {dep}")
            parts.append("")

        # Data Requirements
        if metadata.data_requirements:
            parts.append("## Data Requirements\n")
            for req in metadata.data_requirements:
                parts.append(f"- {req}")
            parts.append("")

        # Rules Summary
        if metadata.rules_summary:
            parts.append("## Rules Summary\n")
            for rule in metadata.rules_summary:
                parts.append(f"- {rule}")
            parts.append("")

        # Limitations
        if metadata.annotation and metadata.annotation.limitations:
            parts.append("## Limitations\n")
            for limitation in metadata.annotation.limitations:
                parts.append(f"- {limitation}")
            parts.append("")

        # Examples
        if metadata.annotation and metadata.annotation.examples:
            parts.append("## Examples\n")
            for example in metadata.annotation.examples:
                parts.append(f"- {example}")
            parts.append("")

        # Drift hash (embedded as HTML comment for machine parsing)
        if metadata.drift:
            parts.append(f"<!-- rules_hash: {metadata.drift.rules_hash} -->")

        # Footer
        sidecar_name = self._sidecar_name(metadata.artifact_type)
        parts.append(f"\n---\n*Auto-generated from {sidecar_name}. Do not edit directly.*")

        return "\n".join(parts) + "\n"

    def write_skill(self, metadata: SkillMetadata, path: Path) -> None:
        """Render and write a SKILL.md file to disk.

        Args:
            metadata: Complete skill metadata for the artifact.
            path: Output path for the SKILL.md file.
        """
        content = self.render_skill(metadata)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _sidecar_name(self, artifact_type: ArtifactType) -> str:
        """Return the expected sidecar filename for an artifact type."""
        if artifact_type == ArtifactType.STRATEGY:
            return "strategy.skill.yaml"
        elif artifact_type == ArtifactType.INDICATOR:
            return "<indicator>.skill.yaml"
        elif artifact_type == ArtifactType.FORMULA:
            return "formulas.skill.yaml"
        return ".skill.yaml"
