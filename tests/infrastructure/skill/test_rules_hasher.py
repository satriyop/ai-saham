"""
Tests for rules hasher (drift detection).

Tests verify:
- compute_hash() returns consistent hash for same content
- compute_hash() returns different hash for different rules
- extract_stored_hash() extracts hash from HTML comment
- extract_stored_hash() returns None for missing file
- extract_stored_hash() returns None when no hash comment
- is_stale() returns True when hashes differ
- is_stale() returns False when hashes match
- is_stale() returns True when SKILL.md doesn't exist

Layer: Infrastructure
"""

from pathlib import Path

from src.infrastructure.skill.rules_hasher import RulesHasher


class TestRulesHasherCompute:
    """Test compute_hash() functionality."""

    def test_compute_hash_returns_consistent_hash_for_same_content(
        self, tmp_path: Path
    ):
        """compute_hash() should return same hash for same rules content."""
        yaml_content = """
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
        strategy_path = tmp_path / "strategy.yaml"
        strategy_path.write_text(yaml_content, encoding="utf-8")

        hasher = RulesHasher()
        hash1 = hasher.compute_hash(strategy_path)
        hash2 = hasher.compute_hash(strategy_path)

        assert hash1 == hash2
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 produces 64-char hex string

    def test_compute_hash_returns_different_hash_for_different_rules(
        self, tmp_path: Path
    ):
        """compute_hash() should return different hashes for different rules."""
        yaml1 = """
indicators:
  rsi:
    type: RSI
    period: 14
rules:
  - name: Entry
    when: rsi < 30
    outcome: buy
"""
        yaml2 = """
indicators:
  rsi:
    type: RSI
    period: 14
rules:
  - name: Entry
    when: rsi < 40
    outcome: buy
"""
        strategy1 = tmp_path / "strategy1.yaml"
        strategy2 = tmp_path / "strategy2.yaml"
        strategy1.write_text(yaml1, encoding="utf-8")
        strategy2.write_text(yaml2, encoding="utf-8")

        hasher = RulesHasher()
        hash1 = hasher.compute_hash(strategy1)
        hash2 = hasher.compute_hash(strategy2)

        assert hash1 != hash2

    def test_compute_hash_ignores_name_and_other_metadata(self, tmp_path: Path):
        """compute_hash() should only hash indicators and rules sections."""
        yaml1 = """
name: Strategy V1
description: Version 1
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    outcome: buy
"""
        yaml2 = """
name: Strategy V2
description: Version 2 with different metadata
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    outcome: buy
"""
        strategy1 = tmp_path / "strategy1.yaml"
        strategy2 = tmp_path / "strategy2.yaml"
        strategy1.write_text(yaml1, encoding="utf-8")
        strategy2.write_text(yaml2, encoding="utf-8")

        hasher = RulesHasher()
        hash1 = hasher.compute_hash(strategy1)
        hash2 = hasher.compute_hash(strategy2)

        # Hashes should be the same since indicators and rules are identical
        assert hash1 == hash2

    def test_compute_hash_changes_when_indicators_change(self, tmp_path: Path):
        """compute_hash() should detect changes in indicators section."""
        yaml1 = """
indicators:
  rsi:
    type: RSI
    period: 14
rules:
  - name: Entry
    outcome: buy
"""
        yaml2 = """
indicators:
  rsi:
    type: RSI
    period: 21
rules:
  - name: Entry
    outcome: buy
"""
        strategy1 = tmp_path / "strategy1.yaml"
        strategy2 = tmp_path / "strategy2.yaml"
        strategy1.write_text(yaml1, encoding="utf-8")
        strategy2.write_text(yaml2, encoding="utf-8")

        hasher = RulesHasher()
        hash1 = hasher.compute_hash(strategy1)
        hash2 = hasher.compute_hash(strategy2)

        assert hash1 != hash2


class TestRulesHasherExtract:
    """Test extract_stored_hash() functionality."""

    def test_extract_stored_hash_extracts_hash_from_html_comment(
        self, tmp_path: Path
    ):
        """extract_stored_hash() should extract hash from HTML comment."""
        skill_content = """
# Test Strategy

Some content here.

<!-- rules_hash: abc123def456789 -->

---
*Auto-generated*
"""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")

        hasher = RulesHasher()
        result = hasher.extract_stored_hash(skill_path)

        assert result == "abc123def456789"

    def test_extract_stored_hash_returns_none_for_missing_file(self, tmp_path: Path):
        """extract_stored_hash() should return None when file doesn't exist."""
        hasher = RulesHasher()
        missing_path = tmp_path / "nonexistent.md"

        result = hasher.extract_stored_hash(missing_path)

        assert result is None

    def test_extract_stored_hash_returns_none_when_no_hash_comment(
        self, tmp_path: Path
    ):
        """extract_stored_hash() should return None when no hash comment exists."""
        skill_content = """
# Test Strategy

No hash comment in this file.

---
*Auto-generated*
"""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")

        hasher = RulesHasher()
        result = hasher.extract_stored_hash(skill_path)

        assert result is None

    def test_extract_stored_hash_handles_whitespace_in_comment(self, tmp_path: Path):
        """extract_stored_hash() should handle extra whitespace in comment."""
        skill_content = """
# Test Strategy

<!--   rules_hash:   xyz789   -->

---
"""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")

        hasher = RulesHasher()
        result = hasher.extract_stored_hash(skill_path)

        assert result == "xyz789"


class TestRulesHasherIsStale:
    """Test is_stale() drift detection."""

    def test_is_stale_returns_false_when_hashes_match(self, tmp_path: Path):
        """is_stale() should return False when hashes match."""
        strategy_yaml = """
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    outcome: buy
"""
        strategy_path = tmp_path / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        # Compute the hash first
        hasher = RulesHasher()
        current_hash = hasher.compute_hash(strategy_path)

        # Create SKILL.md with matching hash
        skill_content = f"""
# Test Strategy

<!-- rules_hash: {current_hash} -->
"""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")

        result = hasher.is_stale(strategy_path, skill_path)

        assert result is False

    def test_is_stale_returns_true_when_hashes_differ(self, tmp_path: Path):
        """is_stale() should return True when hashes differ."""
        strategy_yaml = """
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    outcome: buy
"""
        strategy_path = tmp_path / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        # Create SKILL.md with different hash
        skill_content = """
# Test Strategy

<!-- rules_hash: old_hash_value_that_doesnt_match -->
"""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")

        hasher = RulesHasher()
        result = hasher.is_stale(strategy_path, skill_path)

        assert result is True

    def test_is_stale_returns_true_when_skill_md_doesnt_exist(self, tmp_path: Path):
        """is_stale() should return True when SKILL.md doesn't exist."""
        strategy_yaml = """
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    outcome: buy
"""
        strategy_path = tmp_path / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        skill_path = tmp_path / "nonexistent_SKILL.md"

        hasher = RulesHasher()
        result = hasher.is_stale(strategy_path, skill_path)

        assert result is True

    def test_is_stale_returns_true_when_no_hash_comment_in_skill_md(
        self, tmp_path: Path
    ):
        """is_stale() should return True when SKILL.md has no hash comment."""
        strategy_yaml = """
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    outcome: buy
"""
        strategy_path = tmp_path / "strategy.yaml"
        strategy_path.write_text(strategy_yaml, encoding="utf-8")

        skill_content = """
# Test Strategy

No hash comment here.
"""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")

        hasher = RulesHasher()
        result = hasher.is_stale(strategy_path, skill_path)

        assert result is True

    def test_is_stale_detects_rule_changes(self, tmp_path: Path):
        """is_stale() should detect when rules are modified."""
        # Initial strategy
        strategy_yaml_v1 = """
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    when: rsi < 30
    outcome: buy
"""
        strategy_path = tmp_path / "strategy.yaml"
        strategy_path.write_text(strategy_yaml_v1, encoding="utf-8")

        # Generate SKILL.md with v1 hash
        hasher = RulesHasher()
        v1_hash = hasher.compute_hash(strategy_path)
        skill_content = f"""
# Test Strategy

<!-- rules_hash: {v1_hash} -->
"""
        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")

        # Verify not stale initially
        assert hasher.is_stale(strategy_path, skill_path) is False

        # Modify the strategy (change threshold)
        strategy_yaml_v2 = """
indicators:
  rsi:
    type: RSI
rules:
  - name: Entry
    when: rsi < 40
    outcome: buy
"""
        strategy_path.write_text(strategy_yaml_v2, encoding="utf-8")

        # Now it should be stale
        assert hasher.is_stale(strategy_path, skill_path) is True
