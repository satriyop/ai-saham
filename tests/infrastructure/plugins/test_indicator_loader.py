"""
Tests for IndicatorPluginLoader.

Tests cover:
- Plugin discovery from directory
- Graceful handling of missing directory
- Invalid plugin handling
- Module loading mechanics
"""

import tempfile
from pathlib import Path

import pytest

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.infrastructure.plugins.indicator_loader import IndicatorPluginLoader


# ============================================================================
# Plugin Discovery Tests
# ============================================================================


class TestPluginDiscovery:
    """Test plugin discovery from filesystem."""

    def test_discover_empty_directory(self):
        """Should return empty list for empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = IndicatorPluginLoader(Path(tmpdir))

            plugins = loader.discover()

            assert plugins == []

    def test_discover_missing_directory(self):
        """Should return empty list for missing directory (graceful degradation)."""
        loader = IndicatorPluginLoader(Path("/nonexistent/path"))

        plugins = loader.discover()

        assert plugins == []

    def test_discover_valid_plugin(self):
        """Should discover valid plugin from .py file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_code = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

class TestIndicator(IndicatorPlugin):
    name = "TEST"
    default_period = 7

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        return [Decimal("1.0")] * max(0, len(candles) - period + 1)
'''
            plugin_path = Path(tmpdir) / "test_indicator.py"
            plugin_path.write_text(plugin_code)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert len(plugins) == 1
            assert plugins[0].name == "TEST"
            assert plugins[0].default_period == 7

    def test_discover_multiple_plugins(self):
        """Should discover multiple plugins from directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin1 = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

class Plugin1(IndicatorPlugin):
    name = "PLUGIN1"
    default_period = 5

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        return []
'''
            plugin2 = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

class Plugin2(IndicatorPlugin):
    name = "PLUGIN2"
    default_period = 10

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        return []
'''
            (Path(tmpdir) / "plugin1.py").write_text(plugin1)
            (Path(tmpdir) / "plugin2.py").write_text(plugin2)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert len(plugins) == 2
            names = {p.name for p in plugins}
            assert names == {"PLUGIN1", "PLUGIN2"}

    def test_skip_files_starting_with_underscore(self):
        """Should skip __init__.py and _private.py files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create __init__.py
            (Path(tmpdir) / "__init__.py").write_text("# init")

            # Create _private.py with valid plugin
            private_plugin = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin

class PrivatePlugin(IndicatorPlugin):
    name = "PRIVATE"
    default_period = 5
    def compute(self, candles, period):
        return []
'''
            (Path(tmpdir) / "_private.py").write_text(private_plugin)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            # Should find nothing (both files start with _)
            assert plugins == []


# ============================================================================
# Invalid Plugin Handling Tests
# ============================================================================


class TestInvalidPluginHandling:
    """Test graceful handling of invalid plugins."""

    def test_skip_plugin_missing_name(self):
        """Should skip plugin without name attribute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_plugin = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin

class NoNamePlugin(IndicatorPlugin):
    # Missing: name = "..."
    default_period = 5

    def compute(self, candles, period):
        return []
'''
            (Path(tmpdir) / "no_name.py").write_text(invalid_plugin)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert plugins == []

    def test_skip_plugin_missing_default_period(self):
        """Should skip plugin without default_period attribute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_plugin = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin

class NoPeriodPlugin(IndicatorPlugin):
    name = "NOPERIOD"
    # Missing: default_period = ...

    def compute(self, candles, period):
        return []
'''
            (Path(tmpdir) / "no_period.py").write_text(invalid_plugin)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert plugins == []

    def test_skip_file_with_syntax_error(self):
        """Should skip files with syntax errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_syntax = "def broken(:\n    pass"
            (Path(tmpdir) / "broken.py").write_text(bad_syntax)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert plugins == []

    def test_skip_file_with_import_error(self):
        """Should skip files with import errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_import = '''
import nonexistent_module_12345

from src.application.ports.indicator_plugin import IndicatorPlugin

class BrokenPlugin(IndicatorPlugin):
    name = "BROKEN"
    default_period = 5
    def compute(self, candles, period):
        return []
'''
            (Path(tmpdir) / "bad_import.py").write_text(bad_import)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert plugins == []

    def test_skip_file_without_plugin_class(self):
        """Should skip files that don't contain IndicatorPlugin subclass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            no_plugin = '''
# Just a regular Python file
def some_function():
    return 42

class RegularClass:
    pass
'''
            (Path(tmpdir) / "not_a_plugin.py").write_text(no_plugin)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert plugins == []

    def test_skip_plugin_with_lowercase_name(self):
        """Should skip plugin with lowercase name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_plugin = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin

class LowercasePlugin(IndicatorPlugin):
    name = "lowercase"
    default_period = 5

    def compute(self, candles, period):
        return []
'''
            (Path(tmpdir) / "lowercase.py").write_text(invalid_plugin)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert plugins == []

    def test_skip_plugin_with_special_characters(self):
        """Should skip plugin with special characters in name (e.g., hyphens)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_plugin = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin

class HyphenPlugin(IndicatorPlugin):
    name = "ATR-14"
    default_period = 14

    def compute(self, candles, period):
        return []
'''
            (Path(tmpdir) / "hyphen.py").write_text(invalid_plugin)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert plugins == []

    def test_skip_plugin_with_spaces(self):
        """Should skip plugin with spaces in name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_plugin = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin

class SpacedPlugin(IndicatorPlugin):
    name = "MY INDICATOR"
    default_period = 5

    def compute(self, candles, period):
        return []
'''
            (Path(tmpdir) / "spaced.py").write_text(invalid_plugin)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert plugins == []

    def test_accept_valid_uppercase_name_with_underscore(self):
        """Should accept plugin with uppercase name containing underscore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid_plugin = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

class UnderscorePlugin(IndicatorPlugin):
    name = "ATR_14"
    default_period = 14

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        return []
'''
            (Path(tmpdir) / "underscore.py").write_text(valid_plugin)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert len(plugins) == 1
            assert plugins[0].name == "ATR_14"

    def test_accept_valid_name_with_numbers(self):
        """Should accept plugin with uppercase name containing numbers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid_plugin = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

class NumberPlugin(IndicatorPlugin):
    name = "EMA200"
    default_period = 200

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        return []
'''
            (Path(tmpdir) / "ema200.py").write_text(valid_plugin)

            loader = IndicatorPluginLoader(Path(tmpdir))
            plugins = loader.discover()

            assert len(plugins) == 1
            assert plugins[0].name == "EMA200"


# ============================================================================
# Integration with Real ATR Plugin
# ============================================================================


class TestRealATRPlugin:
    """Test loading the actual ATR plugin from plugins/indicators/."""

    def test_load_atr_plugin(self):
        """Should load ATR plugin from project plugins directory."""
        loader = IndicatorPluginLoader(Path("plugins/indicators"))
        plugins = loader.discover()

        # Should find at least the ATR plugin
        names = {p.name for p in plugins}
        assert "ATR" in names

        # Find ATR plugin and verify attributes
        atr_plugin = next(p for p in plugins if p.name == "ATR")
        assert atr_plugin.default_period == 14
