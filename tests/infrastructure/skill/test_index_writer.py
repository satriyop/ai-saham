"""
Tests for SKILLS_INDEX.md generator.

Tests verify:
- generate() produces markdown with heading
- generate() groups by type (strategies, indicators, formulas)
- generate() includes auto-generated footer
- write() creates SKILLS_INDEX.md file
- Handles project with no SKILL.md files

Layer: Infrastructure
"""

from pathlib import Path

from src.infrastructure.skill.index_writer import SkillIndexWriter


class TestSkillIndexWriterGenerate:
    """Test generate() markdown generation."""

    def test_generate_produces_markdown_with_heading(self, tmp_path: Path):
        """generate() should produce markdown with main heading."""
        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        assert "# Skills Index" in result
        assert "Catalog of all documented artifacts" in result

    def test_generate_groups_by_type_strategies(self, tmp_path: Path):
        """generate() should group strategies in their own section."""
        # Create a strategy SKILL.md
        strategy_dir = tmp_path / "strategies" / "rsi-momentum"
        strategy_dir.mkdir(parents=True)
        skill_md = strategy_dir / "SKILL.md"
        skill_content = """
# RSI Momentum Strategy

**Type:** strategy

## Description

A momentum strategy based on RSI indicator.

## Tags

`momentum`, `reversal`
"""
        skill_md.write_text(skill_content, encoding="utf-8")

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        assert "## Strategies" in result
        assert "RSI Momentum Strategy" in result
        assert "`momentum`" in result

    def test_generate_groups_by_type_indicators(self, tmp_path: Path):
        """generate() should group indicators in their own section."""
        # Create an indicator SKILL.md
        indicator_dir = tmp_path / "plugins" / "indicators"
        indicator_dir.mkdir(parents=True)
        skill_md = indicator_dir / "atr.SKILL.md"
        skill_content = """
# ATR

**Type:** indicator

## Description

Average True Range indicator for volatility.

## Tags

`volatility`
"""
        skill_md.write_text(skill_content, encoding="utf-8")

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        assert "## Indicators" in result
        assert "ATR" in result
        assert "`volatility`" in result

    def test_generate_groups_by_type_formulas(self, tmp_path: Path):
        """generate() should group formulas in their own section."""
        # Create a formula SKILL.md
        formula_dir = tmp_path / "skills" / "formulas"
        formula_dir.mkdir(parents=True)
        skill_md = formula_dir / "SMOOTH_RSI.SKILL.md"
        skill_content = """
# SMOOTH_RSI

**Type:** formula

## Description

RSI with EMA smoothing applied.
"""
        skill_md.write_text(skill_content, encoding="utf-8")

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        assert "## Formulas" in result
        assert "SMOOTH_RSI" in result

    def test_generate_creates_table_with_links(self, tmp_path: Path):
        """generate() should create markdown table with links to SKILL.md files."""
        strategy_dir = tmp_path / "strategies" / "test"
        strategy_dir.mkdir(parents=True)
        skill_md = strategy_dir / "SKILL.md"
        skill_content = """
# Test Strategy

**Type:** strategy

## Description

Test description for the strategy.
"""
        skill_md.write_text(skill_content, encoding="utf-8")

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        assert "| Name | Description | Tags | Link |" in result
        assert "|------|-------------|------|------|" in result
        assert "Test Strategy" in result
        assert "[SKILL.md]" in result
        assert "strategies/test/SKILL.md" in result

    def test_generate_truncates_long_descriptions(self, tmp_path: Path):
        """generate() should truncate descriptions longer than 80 characters."""
        strategy_dir = tmp_path / "strategies" / "test"
        strategy_dir.mkdir(parents=True)
        skill_md = strategy_dir / "SKILL.md"
        long_description = "A" * 100  # 100 characters
        skill_content = f"""
# Test Strategy

**Type:** strategy

## Description

{long_description}
"""
        skill_md.write_text(skill_content, encoding="utf-8")

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        # Description should be truncated to 80 chars
        assert long_description[:80] in result
        assert long_description not in result

    def test_generate_handles_missing_description(self, tmp_path: Path):
        """generate() should handle SKILL.md with no description section."""
        strategy_dir = tmp_path / "strategies" / "test"
        strategy_dir.mkdir(parents=True)
        skill_md = strategy_dir / "SKILL.md"
        skill_content = """
# Test Strategy

**Type:** strategy
"""
        skill_md.write_text(skill_content, encoding="utf-8")

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        assert "Test Strategy" in result
        # Should show em-dash for missing description
        lines = result.split("\n")
        strategy_line = [line for line in lines if "Test Strategy" in line][0]
        assert "—" in strategy_line

    def test_generate_handles_missing_tags(self, tmp_path: Path):
        """generate() should handle SKILL.md with no tags section."""
        strategy_dir = tmp_path / "strategies" / "test"
        strategy_dir.mkdir(parents=True)
        skill_md = strategy_dir / "SKILL.md"
        skill_content = """
# Test Strategy

**Type:** strategy

## Description

Test description
"""
        skill_md.write_text(skill_content, encoding="utf-8")

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        assert "Test Strategy" in result
        lines = result.split("\n")
        strategy_line = [line for line in lines if "Test Strategy" in line][0]
        # Should show em-dash for missing tags
        assert "—" in strategy_line

    def test_generate_skips_todo_placeholders_in_description(self, tmp_path: Path):
        """generate() should skip TODO comment placeholders in description."""
        strategy_dir = tmp_path / "strategies" / "test"
        strategy_dir.mkdir(parents=True)
        skill_md = strategy_dir / "SKILL.md"
        skill_content = """
# Test Strategy

**Type:** strategy

## Description

<!-- TODO: Add description -->
"""
        skill_md.write_text(skill_content, encoding="utf-8")

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        # Should show em-dash since description is just a TODO comment
        lines = result.split("\n")
        strategy_line = [line for line in lines if "Test Strategy" in line][0]
        assert "—" in strategy_line

    def test_generate_includes_auto_generated_footer(self, tmp_path: Path):
        """generate() should include auto-generated footer."""
        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        assert "---" in result
        assert "*Auto-generated by `saham strategy skill index`. Do not edit directly.*" in result

    def test_generate_handles_multiple_skill_files(self, tmp_path: Path):
        """generate() should handle multiple SKILL.md files across types."""
        # Create strategy
        strategy_dir = tmp_path / "strategies" / "momentum"
        strategy_dir.mkdir(parents=True)
        (strategy_dir / "SKILL.md").write_text(
            "# Momentum\n\n**Type:** strategy\n\n## Description\n\nMomentum strategy",
            encoding="utf-8",
        )

        # Create indicator
        indicator_dir = tmp_path / "plugins" / "indicators"
        indicator_dir.mkdir(parents=True)
        (indicator_dir / "rsi.SKILL.md").write_text(
            "# RSI\n\n**Type:** indicator\n\n## Description\n\nRSI indicator",
            encoding="utf-8",
        )

        # Create formula
        formula_dir = tmp_path / "skills" / "formulas"
        formula_dir.mkdir(parents=True)
        (formula_dir / "SMOOTH.SKILL.md").write_text(
            "# SMOOTH\n\n**Type:** formula\n\n## Description\n\nSmoothing formula",
            encoding="utf-8",
        )

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        # All sections should be present
        assert "## Strategies" in result
        assert "## Indicators" in result
        assert "## Formulas" in result
        assert "Momentum" in result
        assert "RSI" in result
        assert "SMOOTH" in result

    def test_generate_skips_node_modules_and_git_directories(self, tmp_path: Path):
        """generate() should skip SKILL.md files in node_modules and .git."""
        # Create SKILL.md in node_modules
        node_modules_dir = tmp_path / "node_modules" / "some-package"
        node_modules_dir.mkdir(parents=True)
        (node_modules_dir / "SKILL.md").write_text(
            "# Should Be Skipped\n\n**Type:** strategy",
            encoding="utf-8",
        )

        # Create SKILL.md in .git
        git_dir = tmp_path / ".git" / "some-path"
        git_dir.mkdir(parents=True)
        (git_dir / "SKILL.md").write_text(
            "# Should Also Be Skipped\n\n**Type:** strategy",
            encoding="utf-8",
        )

        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        assert "Should Be Skipped" not in result
        assert "Should Also Be Skipped" not in result

    def test_generate_handles_empty_project(self, tmp_path: Path):
        """generate() should handle project with no SKILL.md files."""
        writer = SkillIndexWriter()
        result = writer.generate(tmp_path)

        # Should still produce valid markdown
        assert "# Skills Index" in result
        assert "Catalog of all documented artifacts" in result
        assert "*Auto-generated" in result
        # But no type sections since no files found
        assert "## Strategies" not in result
        assert "## Indicators" not in result
        assert "## Formulas" not in result


class TestSkillIndexWriterWrite:
    """Test write() file writing."""

    def test_write_creates_skills_index_file(self, tmp_path: Path):
        """write() should create SKILLS_INDEX.md at project root."""
        writer = SkillIndexWriter()
        output_path = writer.write(tmp_path)

        assert output_path == tmp_path / "SKILLS_INDEX.md"
        assert output_path.exists()

    def test_write_creates_valid_content(self, tmp_path: Path):
        """write() should create file with valid markdown content."""
        # Create a strategy SKILL.md
        strategy_dir = tmp_path / "strategies" / "test"
        strategy_dir.mkdir(parents=True)
        (strategy_dir / "SKILL.md").write_text(
            "# Test\n\n**Type:** strategy\n\n## Description\n\nTest strategy",
            encoding="utf-8",
        )

        writer = SkillIndexWriter()
        output_path = writer.write(tmp_path)

        content = output_path.read_text(encoding="utf-8")
        assert "# Skills Index" in content
        assert "## Strategies" in content
        assert "Test" in content

    def test_write_overwrites_existing_file(self, tmp_path: Path):
        """write() should overwrite existing SKILLS_INDEX.md."""
        index_path = tmp_path / "SKILLS_INDEX.md"
        index_path.write_text("Old content", encoding="utf-8")

        writer = SkillIndexWriter()
        output_path = writer.write(tmp_path)

        content = output_path.read_text(encoding="utf-8")
        assert "Old content" not in content
        assert "# Skills Index" in content
