"""
Tests for skill CLI commands.

Tests verify:
- skill check command runs without error
- skill index command creates SKILLS_INDEX.md
- Commands use typer.testing.CliRunner

Note: Testing strategy validate + skill generate integration is complex
and better suited for integration tests. These tests focus on the
skill-specific commands that can be tested in isolation.

Layer: Adapter
"""

from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.strategy_skill_commands import skill_app


runner = CliRunner()


class TestSkillCheckCommand:
    """Test 'skill check' command."""

    def test_check_command_runs_without_error_on_empty_project(
        self, tmp_path: Path, monkeypatch
    ):
        """skill check should run successfully even with no artifacts."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(skill_app, ["check"])

        assert result.exit_code == 0
        assert "No artifacts found to check" in result.stdout

    def test_check_command_reports_strategy_with_no_skill_md(
        self, tmp_path: Path, monkeypatch
    ):
        """skill check should report strategies missing SKILL.md."""
        # Create a strategy without SKILL.md
        strategy_dir = tmp_path / "strategies" / "test-strategy"
        strategy_dir.mkdir(parents=True)
        strategy_yaml = """
name: Test Strategy
indicators: {}
rules: []
"""
        (strategy_dir / "strategy.yaml").write_text(strategy_yaml, encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(skill_app, ["check"])

        assert result.exit_code == 0
        assert "test-strategy: no SKILL.md" in result.stdout
        assert "1/1 artifact(s) need regeneration" in result.stdout

    def test_check_command_reports_up_to_date_strategy(
        self, tmp_path: Path, monkeypatch
    ):
        """skill check should report strategies that are up to date."""
        from src.infrastructure.skill.rules_hasher import RulesHasher

        # Create strategy
        strategy_dir = tmp_path / "strategies" / "test-strategy"
        strategy_dir.mkdir(parents=True)
        strategy_yaml = """
name: Test Strategy
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    outcome: buy
"""
        strategy_path = strategy_dir / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        # Generate SKILL.md with correct hash
        hasher = RulesHasher()
        current_hash = hasher.compute_hash(strategy_path)
        skill_content = f"""
# Test Strategy

<!-- rules_hash: {current_hash} -->
"""
        (strategy_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(skill_app, ["check"])

        assert result.exit_code == 0
        assert "test-strategy: up to date" in result.stdout
        assert "All 1 artifact(s) are up to date" in result.stdout

    def test_check_command_reports_stale_strategy(self, tmp_path: Path, monkeypatch):
        """skill check should report strategies with stale SKILL.md."""
        # Create strategy
        strategy_dir = tmp_path / "strategies" / "test-strategy"
        strategy_dir.mkdir(parents=True)
        strategy_yaml = """
name: Test Strategy
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    outcome: buy
"""
        (strategy_dir / "strategy.yaml").write_text(strategy_yaml, encoding="utf-8")

        # Create SKILL.md with wrong hash
        skill_content = """
# Test Strategy

<!-- rules_hash: old_incorrect_hash -->
"""
        (strategy_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(skill_app, ["check"])

        assert result.exit_code == 0
        assert "test-strategy: STALE" in result.stdout
        assert "1/1 artifact(s) need regeneration" in result.stdout

    def test_check_command_handles_multiple_strategies(
        self, tmp_path: Path, monkeypatch
    ):
        """skill check should check multiple strategies."""
        from src.infrastructure.skill.rules_hasher import RulesHasher

        # Create first strategy (up to date)
        strategy1_dir = tmp_path / "strategies" / "strategy1"
        strategy1_dir.mkdir(parents=True)
        strategy1_yaml = """
indicators: {}
rules: []
"""
        strategy1_path = strategy1_dir / "strategy.yaml"
        strategy1_path.write_text(strategy1_yaml, encoding="utf-8")

        hasher = RulesHasher()
        hash1 = hasher.compute_hash(strategy1_path)
        (strategy1_dir / "SKILL.md").write_text(
            f"# Strategy1\n\n<!-- rules_hash: {hash1} -->", encoding="utf-8"
        )

        # Create second strategy (missing SKILL.md)
        strategy2_dir = tmp_path / "strategies" / "strategy2"
        strategy2_dir.mkdir(parents=True)
        (strategy2_dir / "strategy.yaml").write_text(
            "indicators: {}\nrules: []", encoding="utf-8"
        )

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(skill_app, ["check"])

        assert result.exit_code == 0
        assert "strategy1: up to date" in result.stdout
        assert "strategy2: no SKILL.md" in result.stdout
        assert "1/2 artifact(s) need regeneration" in result.stdout


class TestSkillIndexCommand:
    """Test 'skill index' command."""

    def test_index_command_creates_skills_index_file(
        self, tmp_path: Path, monkeypatch
    ):
        """skill index should create SKILLS_INDEX.md."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(skill_app, ["index"])

        assert result.exit_code == 0
        assert "Generated:" in result.stdout

        index_path = tmp_path / "SKILLS_INDEX.md"
        assert index_path.exists()

    def test_index_command_generates_valid_content(self, tmp_path: Path, monkeypatch):
        """skill index should generate valid markdown content."""
        # Create a strategy SKILL.md
        strategy_dir = tmp_path / "strategies" / "test"
        strategy_dir.mkdir(parents=True)
        skill_content = """
# Test Strategy

**Type:** strategy

## Description

Test strategy description
"""
        (strategy_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(skill_app, ["index"])

        assert result.exit_code == 0

        index_path = tmp_path / "SKILLS_INDEX.md"
        content = index_path.read_text(encoding="utf-8")
        assert "# Skills Index" in content
        assert "## Strategies" in content
        assert "Test Strategy" in content

    def test_index_command_accepts_custom_root(self, tmp_path: Path):
        """skill index should accept --root option."""
        project_root = tmp_path / "my-project"
        project_root.mkdir()

        # Create a SKILL.md in the custom root
        strategy_dir = project_root / "strategies" / "test"
        strategy_dir.mkdir(parents=True)
        (strategy_dir / "SKILL.md").write_text(
            "# Test\n\n**Type:** strategy", encoding="utf-8"
        )

        result = runner.invoke(skill_app, ["index", "--root", str(project_root)])

        assert result.exit_code == 0

        index_path = project_root / "SKILLS_INDEX.md"
        assert index_path.exists()

    def test_index_command_overwrites_existing_file(
        self, tmp_path: Path, monkeypatch
    ):
        """skill index should overwrite existing SKILLS_INDEX.md."""
        # Create old index
        index_path = tmp_path / "SKILLS_INDEX.md"
        index_path.write_text("Old content", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(skill_app, ["index"])

        assert result.exit_code == 0

        content = index_path.read_text(encoding="utf-8")
        assert "Old content" not in content
        assert "# Skills Index" in content


class TestSkillGenerateCommand:
    """Test 'skill generate' command (basic smoke tests)."""

    def test_generate_command_fails_for_missing_strategy(
        self, tmp_path: Path, monkeypatch
    ):
        """skill generate should fail gracefully for missing strategy."""
        monkeypatch.chdir(tmp_path)
        # Create strategies directory but no actual strategy
        (tmp_path / "strategies").mkdir()

        result = runner.invoke(skill_app, ["generate", "nonexistent-strategy"])

        assert result.exit_code != 0
        # Error messages may be in stderr or stdout depending on typer configuration
        output = result.stdout + result.stderr
        # Just verify the command failed with non-zero exit code
        assert result.exit_code == 1

    def test_generate_command_requires_artifact_name(self):
        """skill generate should require an artifact name argument."""
        result = runner.invoke(skill_app, ["generate"])

        assert result.exit_code != 0
        # Typer will show usage/error for missing argument

    def test_generate_command_accepts_type_option(self, tmp_path: Path, monkeypatch):
        """skill generate should accept --type option."""
        monkeypatch.chdir(tmp_path)

        # Test with indicator type (will fail due to missing plugin, but validates flag parsing)
        result = runner.invoke(
            skill_app, ["generate", "test", "--type", "indicator"]
        )

        # Command should parse correctly (even if it fails due to missing file)
        # The important thing is it doesn't fail on argument parsing
        # Just verify the command failed with non-zero exit code (missing file, not arg parsing error)
        assert result.exit_code == 1
