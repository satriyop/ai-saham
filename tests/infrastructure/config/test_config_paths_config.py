"""Verify ConfigPathsConfig exposes the five evidence/context path fields.

Layer: Test (infrastructure config).
"""

from src.infrastructure.config.app_config import ConfigPathsConfig


class TestConfigPathsConfigEvidenceFields:
    """The five evidence/context config paths must exist on the dataclass
    with their shipped default values.
    """

    def test_default_values(self):
        cfg = ConfigPathsConfig()
        assert cfg.company_quality_context == "config/company_quality_context.yaml"
        assert cfg.sector_context == "config/sector_context.yaml"
        assert cfg.ticker_profile == "config/ticker_profile.yaml"
        assert cfg.institutional_accumulation == "config/institutional_accumulation.yaml"
        assert cfg.universes == "config/universes.yaml"

    def test_load_app_config_populates_them(self):
        """Verify load_app_config() returns ConfigPathsConfig with the
        five fields set from default.yaml (not just dataclass fallbacks)."""
        from src.infrastructure.config.app_config import load_app_config

        cfg = load_app_config()
        paths = cfg.config_paths
        assert paths.company_quality_context == "config/company_quality_context.yaml"
        assert paths.sector_context == "config/sector_context.yaml"
        assert paths.ticker_profile == "config/ticker_profile.yaml"
        assert paths.institutional_accumulation == "config/institutional_accumulation.yaml"
        assert paths.universes == "config/universes.yaml"

    def test_can_override_via_constructor(self):
        cfg = ConfigPathsConfig(
            company_quality_context="override/cq.yaml",
            sector_context="override/sc.yaml",
            ticker_profile="override/tp.yaml",
            institutional_accumulation="override/ia.yaml",
            universes="override/uni.yaml",
        )
        assert cfg.company_quality_context == "override/cq.yaml"
        assert cfg.sector_context == "override/sc.yaml"
        assert cfg.ticker_profile == "override/tp.yaml"
        assert cfg.institutional_accumulation == "override/ia.yaml"
        assert cfg.universes == "override/uni.yaml"
