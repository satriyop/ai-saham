"""
Tests for skill generator service.

Tests verify:
- generate_for_strategy() produces SkillGenerationResult with success=True
- generate_for_strategy() reads strategy.yaml and sidecar
- generate_for_strategy() warns when sidecar is missing
- generate_for_strategy() detects broker data requirements from FOREIGN_FLOW indicators
- generate_for_strategy() extracts dependencies (indicator types)
- generate_for_strategy() extracts rules summary
- generate_for_strategy() detects drift
- generate_for_indicator() works for plugin indicators
- generate_for_formula() works for formula artifacts

Layer: Application
"""

from pathlib import Path

import pytest

from src.application.services.skill_generator import (
    SkillGeneratorService,
    SkillGenerationResult,
)
from src.domain.value_objects.skill_annotation import ArtifactType
from src.infrastructure.skill.annotation_reader import AnnotationReader
from src.infrastructure.skill.markdown_writer import MarkdownSkillWriter
from src.infrastructure.skill.rules_hasher import RulesHasher


class TestSkillGeneratorStrategy:
    """Test generate_for_strategy() functionality."""

    def test_generate_for_strategy_returns_success_result(self, tmp_path: Path):
        """generate_for_strategy() should return success result."""
        strategy_yaml = """
name: Test Strategy
indicators:
  rsi:
    type: RSI
    period: 14
rules:
  - name: Entry
    when: rsi < 30
    outcome: buy
"""
        strategy_dir = tmp_path / "test-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        sidecar_yaml = """
description: Test strategy for momentum
when_to_use: When RSI shows oversold conditions
"""
        sidecar_path = strategy_dir / "strategy.skill.yaml"
        sidecar_path.write_text(sidecar_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_strategy(strategy_path)

        assert isinstance(result, SkillGenerationResult)
        assert result.success is True
        assert result.output_path is not None
        assert result.output_path == strategy_dir / "SKILL.md"
        assert result.output_path.exists()

    def test_generate_for_strategy_reads_sidecar_annotation(self, tmp_path: Path):
        """generate_for_strategy() should read and include sidecar annotation."""
        strategy_yaml = """
name: Test Strategy
indicators: {}
rules: []
"""
        strategy_dir = tmp_path / "test-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        sidecar_yaml = """
description: Momentum trading strategy
when_to_use: When market shows clear trend
tags:
  - momentum
  - trend
"""
        sidecar_path = strategy_dir / "strategy.skill.yaml"
        sidecar_path.write_text(sidecar_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_strategy(strategy_path)

        assert result.success is True
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "Momentum trading strategy" in skill_content
        assert "When market shows clear trend" in skill_content
        assert "`momentum`" in skill_content

    def test_generate_for_strategy_warns_when_sidecar_missing(self, tmp_path: Path):
        """generate_for_strategy() should warn when sidecar doesn't exist."""
        strategy_yaml = """
name: Test Strategy
indicators: {}
rules: []
"""
        strategy_dir = tmp_path / "test-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")
        # No sidecar created

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_strategy(strategy_path)

        assert result.success is True
        assert len(result.warnings) > 0
        assert any("No sidecar found" in w for w in result.warnings)

    def test_generate_for_strategy_extracts_dependencies(self, tmp_path: Path):
        """generate_for_strategy() should extract indicator types as dependencies."""
        strategy_yaml = """
name: Test Strategy
indicators:
  rsi_14:
    type: RSI
    period: 14
  sma_50:
    type: SMA
    period: 50
  ema_20:
    type: EMA
    period: 20
rules: []
"""
        strategy_dir = tmp_path / "test-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_strategy(strategy_path)

        assert result.success is True
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "## Dependencies" in skill_content
        assert "- EMA" in skill_content
        assert "- RSI" in skill_content
        assert "- SMA" in skill_content

    def test_generate_for_strategy_detects_broker_data_requirements(
        self, tmp_path: Path
    ):
        """generate_for_strategy() should detect broker_flow requirement from FOREIGN_FLOW indicators."""
        strategy_yaml = """
name: Foreign Flow Strategy
indicators:
  foreign_buy:
    type: FOREIGN_FLOW
    direction: buy
  rsi:
    type: RSI
rules: []
"""
        strategy_dir = tmp_path / "test-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_strategy(strategy_path)

        assert result.success is True
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "## Data Requirements" in skill_content
        assert "- broker_flow" in skill_content
        assert "- ohlcv" in skill_content  # Always included

    def test_generate_for_strategy_detects_ohlcv_only_for_regular_indicators(
        self, tmp_path: Path
    ):
        """generate_for_strategy() should only require ohlcv for regular indicators."""
        strategy_yaml = """
name: Simple Strategy
indicators:
  rsi:
    type: RSI
  sma:
    type: SMA
rules: []
"""
        strategy_dir = tmp_path / "test-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_strategy(strategy_path)

        assert result.success is True
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "- ohlcv" in skill_content
        assert "broker_flow" not in skill_content

    def test_generate_for_strategy_extracts_rules_summary(self, tmp_path: Path):
        """generate_for_strategy() should extract rules summary."""
        strategy_yaml = """
name: Test Strategy
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry Signal
    when: rsi < 30
    rationale: RSI shows oversold condition
    outcome: buy
  - name: Exit Signal
    when: rsi > 70
    rationale: RSI shows overbought condition
    outcome: sell
"""
        strategy_dir = tmp_path / "test-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_strategy(strategy_path)

        assert result.success is True
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "## Rules Summary" in skill_content
        assert "**Entry Signal** (buy): RSI shows oversold condition" in skill_content
        assert "**Exit Signal** (sell): RSI shows overbought condition" in skill_content

    def test_generate_for_strategy_detects_drift_when_rules_change(
        self, tmp_path: Path
    ):
        """generate_for_strategy() should detect drift when rules have changed."""
        strategy_yaml_v1 = """
name: Test Strategy
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    when: rsi < 30
    outcome: buy
"""
        strategy_dir = tmp_path / "test-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml_v1, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        # Generate first version
        result1 = generator.generate_for_strategy(strategy_path)
        assert result1.success is True
        assert result1.drift_detected is False

        # Modify strategy rules
        strategy_yaml_v2 = """
name: Test Strategy
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    when: rsi < 40
    outcome: buy
"""
        strategy_path.write_text(strategy_yaml_v2, encoding="utf-8")

        # Generate again
        result2 = generator.generate_for_strategy(strategy_path)
        assert result2.success is True
        assert result2.drift_detected is True
        assert any("SKILL.md is stale" in w for w in result2.warnings)

    def test_generate_for_strategy_includes_cli_usage(self, tmp_path: Path):
        """generate_for_strategy() should include CLI usage examples."""
        strategy_yaml = """
name: Test Strategy
indicators: {}
rules: []
"""
        strategy_dir = tmp_path / "my-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_strategy(strategy_path)

        assert result.success is True
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "## CLI Usage" in skill_content
        assert "saham strategy validate my-strategy" in skill_content
        assert "saham backtest BBCA --strategy my-strategy" in skill_content

    def test_generate_for_strategy_returns_failure_for_invalid_yaml(
        self, tmp_path: Path
    ):
        """generate_for_strategy() should return failure for malformed YAML."""
        strategy_yaml = """
name: Test
invalid yaml syntax here
  bad indentation
"""
        strategy_dir = tmp_path / "test-strategy"
        strategy_dir.mkdir()
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_strategy(strategy_path)

        assert result.success is False
        assert result.output_path is None
        assert len(result.warnings) > 0


class TestSkillGeneratorIndicator:
    """Test generate_for_indicator() functionality."""

    def test_generate_for_indicator_returns_success_result(self, tmp_path: Path):
        """generate_for_indicator() should generate SKILL.md for indicator."""
        plugin_dir = tmp_path / "plugins" / "indicators"
        plugin_dir.mkdir(parents=True)
        plugin_path = plugin_dir / "atr.py"
        plugin_path.write_text("# Indicator plugin code", encoding="utf-8")

        sidecar_yaml = """
description: Average True Range indicator
when_to_use: To measure market volatility
tags:
  - volatility
"""
        sidecar_path = plugin_dir / "atr.skill.yaml"
        sidecar_path.write_text(sidecar_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_indicator(plugin_path)

        assert result.success is True
        assert result.output_path is not None
        assert result.output_path == plugin_dir / "atr.SKILL.md"
        assert result.output_path.exists()
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "# ATR" in skill_content
        assert "Average True Range indicator" in skill_content

    def test_generate_for_indicator_includes_cli_usage(self, tmp_path: Path):
        """generate_for_indicator() should include CLI usage examples."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_path = plugin_dir / "macd.py"
        plugin_path.write_text("# MACD plugin", encoding="utf-8")

        sidecar_yaml = """
description: MACD indicator
when_to_use: For trend following
"""
        sidecar_path = plugin_dir / "macd.skill.yaml"
        sidecar_path.write_text(sidecar_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_indicator(plugin_path)

        assert result.success is True
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "saham compute MACD BBCA" in skill_content

    def test_generate_for_indicator_warns_when_sidecar_missing(self, tmp_path: Path):
        """generate_for_indicator() should warn when sidecar is missing."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_path = plugin_dir / "custom.py"
        plugin_path.write_text("# Custom plugin", encoding="utf-8")
        # No sidecar

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        result = generator.generate_for_indicator(plugin_path)

        assert result.success is True
        assert any("No sidecar found" in w for w in result.warnings)


class TestSkillGeneratorFormula:
    """Test generate_for_formula() functionality."""

    def test_generate_for_formula_returns_success_result(self, tmp_path: Path):
        """generate_for_formula() should generate SKILL.md for formula."""
        formulas_yaml = """
SMOOTH_RSI:
  expression: EMA(RSI(close, 14), 5)
"""
        formulas_path = tmp_path / "formulas.yaml"
        formulas_path.write_text(formulas_yaml, encoding="utf-8")

        sidecar_yaml = """
SMOOTH_RSI:
  description: RSI with EMA smoothing
  when_to_use: When you need smoother RSI values
  tags:
    - smoothing
"""
        sidecar_path = tmp_path / "formulas.skill.yaml"
        sidecar_path.write_text(sidecar_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        output_dir = tmp_path / "skills" / "formulas"
        result = generator.generate_for_formula(
            "SMOOTH_RSI", formulas_path, output_dir=output_dir
        )

        assert result.success is True
        assert result.output_path is not None
        assert result.output_path.name == "SMOOTH_RSI.SKILL.md"
        assert result.output_path.exists()
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "# SMOOTH_RSI" in skill_content
        assert "RSI with EMA smoothing" in skill_content

    def test_generate_for_formula_creates_in_skills_formulas_directory(
        self, tmp_path: Path
    ):
        """generate_for_formula() should create SKILL.md in skills/formulas/ directory."""
        formulas_path = tmp_path / "formulas.yaml"
        formulas_path.write_text("MOMENTUM_SCORE: {}", encoding="utf-8")

        sidecar_yaml = """
MOMENTUM_SCORE:
  description: Composite momentum score
  when_to_use: For multi-factor analysis
"""
        sidecar_path = tmp_path / "formulas.skill.yaml"
        sidecar_path.write_text(sidecar_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        output_dir = tmp_path / "skills" / "formulas"
        result = generator.generate_for_formula(
            "MOMENTUM_SCORE", formulas_path, output_dir=output_dir
        )

        assert result.success is True
        expected_dir = tmp_path / "skills" / "formulas"
        assert result.output_path.parent == expected_dir
        assert expected_dir.exists()

    def test_generate_for_formula_warns_when_annotation_missing(self, tmp_path: Path):
        """generate_for_formula() should warn when formula annotation is missing."""
        formulas_path = tmp_path / "formulas.yaml"
        formulas_path.write_text("{}", encoding="utf-8")

        sidecar_yaml = """
OTHER_FORMULA:
  description: Some other formula
  when_to_use: Sometimes
"""
        sidecar_path = tmp_path / "formulas.skill.yaml"
        sidecar_path.write_text(sidecar_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        output_dir = tmp_path / "skills" / "formulas"
        result = generator.generate_for_formula(
            "MISSING_FORMULA", formulas_path, output_dir=output_dir
        )

        assert result.success is True
        assert any("No annotation found for formula 'MISSING_FORMULA'" in w for w in result.warnings)

    def test_generate_for_formula_includes_cli_usage(self, tmp_path: Path):
        """generate_for_formula() should include CLI usage examples."""
        formulas_path = tmp_path / "formulas.yaml"
        formulas_path.write_text("{}", encoding="utf-8")

        sidecar_yaml = """
TEST_FORMULA:
  description: Test formula
  when_to_use: For testing
"""
        sidecar_path = tmp_path / "formulas.skill.yaml"
        sidecar_path.write_text(sidecar_yaml, encoding="utf-8")

        generator = SkillGeneratorService(
            annotation_reader=AnnotationReader(),
            skill_writer=MarkdownSkillWriter(),
            rules_hasher=RulesHasher(),
        )

        output_dir = tmp_path / "skills" / "formulas"
        result = generator.generate_for_formula(
            "TEST_FORMULA", formulas_path, output_dir=output_dir
        )

        assert result.success is True
        skill_content = result.output_path.read_text(encoding="utf-8")
        assert "saham compute TEST_FORMULA BBCA" in skill_content
