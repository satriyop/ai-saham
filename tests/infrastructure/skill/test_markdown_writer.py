"""
Tests for markdown SKILL.md writer.

Tests verify:
- render_skill() produces correct markdown structure
- render_skill() includes all metadata sections
- render_skill() handles missing annotation (None) with TODO placeholders
- render_skill() embeds rules_hash as HTML comment
- render_skill() includes auto-generated footer
- write_skill() creates file on disk
- write_skill() creates parent directories

Layer: Infrastructure
"""

from pathlib import Path

from src.domain.value_objects.skill_annotation import (
    ArtifactType,
    DriftInfo,
    SkillAnnotation,
    SkillMetadata,
)
from src.infrastructure.skill.markdown_writer import MarkdownSkillWriter


class TestMarkdownSkillWriterRender:
    """Test render_skill() markdown generation."""

    def test_render_includes_heading_with_artifact_name(self):
        """render_skill() should include artifact name as heading."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="RSI Momentum",
            artifact_path=Path("/test/strategy.yaml"),
            annotation=None,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "# RSI Momentum" in result
        assert "**Type:** STRATEGY" in result

    def test_render_includes_description_from_annotation(self):
        """render_skill() should include description when annotation exists."""
        annotation = SkillAnnotation(
            description="Test strategy description",
            when_to_use="When market is trending",
        )
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=annotation,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## Description" in result
        assert "Test strategy description" in result

    def test_render_includes_todo_when_annotation_is_none(self):
        """render_skill() should show TODO when annotation is missing."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test/strategy.yaml"),
            annotation=None,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## Description" in result
        assert "<!-- TODO: Add description in strategy.skill.yaml -->" in result
        assert "## When to Use" in result
        assert "<!-- TODO: Add when_to_use in strategy.skill.yaml -->" in result

    def test_render_includes_when_to_use_from_annotation(self):
        """render_skill() should include when_to_use section."""
        annotation = SkillAnnotation(
            description="Test",
            when_to_use="Use during volatile markets",
        )
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=annotation,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## When to Use" in result
        assert "Use during volatile markets" in result

    def test_render_includes_tags_as_inline_code(self):
        """render_skill() should render tags as inline code blocks."""
        annotation = SkillAnnotation(
            description="Test",
            when_to_use="Test",
            tags=("momentum", "technical", "reversal"),
        )
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=annotation,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## Tags" in result
        assert "`momentum`" in result
        assert "`technical`" in result
        assert "`reversal`" in result

    def test_render_omits_tags_section_when_empty(self):
        """render_skill() should not include tags section if no tags."""
        annotation = SkillAnnotation(
            description="Test",
            when_to_use="Test",
            tags=(),
        )
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=annotation,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        # Should not include Tags section when empty
        lines = result.split("\n")
        tag_headers = [line for line in lines if line.strip() == "## Tags"]
        assert len(tag_headers) == 0

    def test_render_includes_cli_usage_in_code_block(self):
        """render_skill() should include CLI usage examples in code block."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
            cli_usage=("saham strategy validate test", "saham backtest BBCA --strategy test"),
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## CLI Usage" in result
        assert "```bash" in result
        assert "saham strategy validate test" in result
        assert "saham backtest BBCA --strategy test" in result

    def test_render_includes_dependencies_list(self):
        """render_skill() should include dependencies as bulleted list."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
            dependencies=("RSI", "SMA", "EMA"),
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## Dependencies" in result
        assert "- RSI" in result
        assert "- SMA" in result
        assert "- EMA" in result

    def test_render_includes_data_requirements(self):
        """render_skill() should include data requirements list."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
            data_requirements=("ohlcv", "broker_flow"),
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## Data Requirements" in result
        assert "- ohlcv" in result
        assert "- broker_flow" in result

    def test_render_includes_rules_summary(self):
        """render_skill() should include rules summary list."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
            rules_summary=(
                "**Entry Rule** (buy): RSI below 30",
                "**Exit Rule** (sell): RSI above 70",
            ),
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## Rules Summary" in result
        assert "- **Entry Rule** (buy): RSI below 30" in result
        assert "- **Exit Rule** (sell): RSI above 70" in result

    def test_render_includes_limitations(self):
        """render_skill() should include limitations from annotation."""
        annotation = SkillAnnotation(
            description="Test",
            when_to_use="Test",
            limitations=("Requires 14 days of data", "May lag in volatile markets"),
        )
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=annotation,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## Limitations" in result
        assert "- Requires 14 days of data" in result
        assert "- May lag in volatile markets" in result

    def test_render_includes_examples(self):
        """render_skill() should include examples from annotation."""
        annotation = SkillAnnotation(
            description="Test",
            when_to_use="Test",
            examples=(
                "Use with 50-period SMA for confirmation",
                "Combine with volume analysis",
            ),
        )
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=annotation,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "## Examples" in result
        assert "- Use with 50-period SMA" in result
        assert "- Combine with volume analysis" in result

    def test_render_embeds_rules_hash_as_html_comment(self):
        """render_skill() should embed drift rules_hash as HTML comment."""
        drift = DriftInfo(
            rules_hash="abc123def456",
            is_stale=False,
            stored_hash=None,
        )
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
            drift=drift,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "<!-- rules_hash: abc123def456 -->" in result

    def test_render_omits_rules_hash_when_drift_is_none(self):
        """render_skill() should not include hash comment when drift is None."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.INDICATOR,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
            drift=None,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "rules_hash:" not in result

    def test_render_includes_auto_generated_footer(self):
        """render_skill() should include auto-generated footer."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test/strategy.yaml"),
            annotation=None,
        )

        writer = MarkdownSkillWriter()
        result = writer.render_skill(metadata)

        assert "---" in result
        assert "*Auto-generated from strategy.skill.yaml. Do not edit directly.*" in result

    def test_render_footer_varies_by_artifact_type(self):
        """render_skill() should customize footer based on artifact type."""
        writer = MarkdownSkillWriter()

        # Strategy
        strategy_meta = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
        )
        strategy_result = writer.render_skill(strategy_meta)
        assert "strategy.skill.yaml" in strategy_result

        # Indicator
        indicator_meta = SkillMetadata(
            artifact_type=ArtifactType.INDICATOR,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
        )
        indicator_result = writer.render_skill(indicator_meta)
        assert "<indicator>.skill.yaml" in indicator_result

        # Formula
        formula_meta = SkillMetadata(
            artifact_type=ArtifactType.FORMULA,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
        )
        formula_result = writer.render_skill(formula_meta)
        assert "formulas.skill.yaml" in formula_result


class TestMarkdownSkillWriterWrite:
    """Test write_skill() file writing."""

    def test_write_skill_creates_file_on_disk(self, tmp_path: Path):
        """write_skill() should create SKILL.md file."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test Strategy",
            artifact_path=Path("/test/strategy.yaml"),
            annotation=None,
        )

        writer = MarkdownSkillWriter()
        output_path = tmp_path / "SKILL.md"
        writer.write_skill(metadata, output_path)

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "# Test Strategy" in content

    def test_write_skill_creates_parent_directories(self, tmp_path: Path):
        """write_skill() should create parent directories if they don't exist."""
        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="Test",
            artifact_path=Path("/test"),
            annotation=None,
        )

        writer = MarkdownSkillWriter()
        output_path = tmp_path / "nested" / "dir" / "SKILL.md"
        writer.write_skill(metadata, output_path)

        assert output_path.exists()
        assert output_path.parent.exists()

    def test_write_skill_overwrites_existing_file(self, tmp_path: Path):
        """write_skill() should overwrite existing SKILL.md."""
        output_path = tmp_path / "SKILL.md"
        output_path.write_text("Old content", encoding="utf-8")

        metadata = SkillMetadata(
            artifact_type=ArtifactType.STRATEGY,
            artifact_name="New Strategy",
            artifact_path=Path("/test"),
            annotation=None,
        )

        writer = MarkdownSkillWriter()
        writer.write_skill(metadata, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "Old content" not in content
        assert "# New Strategy" in content
