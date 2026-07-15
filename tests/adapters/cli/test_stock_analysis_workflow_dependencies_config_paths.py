"""Verify evidence/context config paths come from AppConfig in the dep bundle.

Layer: Test (adapter composition bundle — config path wiring only).
"""

from unittest.mock import MagicMock, patch

from src.adapters.cli.stock_analysis_workflow_dependencies import (
    create_stock_analysis_workflow_dependencies,
)
from src.infrastructure.config.app_config import (
    AppConfig,
    ConfigPathsConfig,
)


class TestConfigPathsFromAppConfig:
    """Monkeypath load_app_config and underlying loaders, then assert
    AppConfig paths are passed through to each evidence/context factory."""

    CUSTOM_PATHS = ConfigPathsConfig(
        company_quality_context="custom/company_quality.yaml",
        sector_context="custom/sector.yaml",
        ticker_profile="custom/ticker.yaml",
        institutional_accumulation="custom/inst_accum.yaml",
        universes="custom/universes.yaml",
    )

    def _make_custom_app_config(self) -> AppConfig:
        return AppConfig(config_paths=self.CUSTOM_PATHS)

    # --- patching helpers ---

    def test_ticker_profile_classifier_uses_app_config_paths(self, tmp_path):
        app_cfg = self._make_custom_app_config()
        sentinel = MagicMock()

        with (
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".load_app_config",
                return_value=app_cfg,
            ),
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".create_ticker_profile_classifier",
                return_value=sentinel,
            ) as mock_ctor,
        ):
            deps = create_stock_analysis_workflow_dependencies(tmp_path / "data.db")
            result = deps.ticker_profile_classifier_factory()

        assert result is sentinel
        mock_ctor.assert_called_once_with(
            profile_path=self.CUSTOM_PATHS.ticker_profile,
            universes_path=self.CUSTOM_PATHS.universes,
        )

    def test_institutional_accumulation_config_uses_app_config_paths(
        self, tmp_path
    ):
        app_cfg = self._make_custom_app_config()
        sentinel = MagicMock()

        with (
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".load_app_config",
                return_value=app_cfg,
            ),
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".load_institutional_accumulation_config",
                return_value=sentinel,
            ) as mock_ctor,
        ):
            deps = create_stock_analysis_workflow_dependencies(tmp_path / "data.db")
            result = deps.institutional_accumulation_config_factory()

        assert result is sentinel
        mock_ctor.assert_called_once_with(
            path=self.CUSTOM_PATHS.institutional_accumulation,
        )

    def test_sector_context_builder_uses_app_config_paths(self, tmp_path):
        app_cfg = self._make_custom_app_config()
        sentinel = MagicMock()

        with (
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".load_app_config",
                return_value=app_cfg,
            ),
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".create_sector_context_evidence_builder",
                return_value=sentinel,
            ) as mock_ctor,
        ):
            deps = create_stock_analysis_workflow_dependencies(tmp_path / "data.db")
            result = deps.sector_context_builder_factory()

        assert result is sentinel
        mock_ctor.assert_called_once_with(
            config_path=self.CUSTOM_PATHS.sector_context,
            universes_path=self.CUSTOM_PATHS.universes,
        )

    def test_company_quality_context_builder_uses_app_config_paths(
        self, tmp_path
    ):
        app_cfg = self._make_custom_app_config()
        sentinel = MagicMock()

        with (
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".load_app_config",
                return_value=app_cfg,
            ),
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".create_company_quality_context_evidence_builder",
                return_value=sentinel,
            ) as mock_ctor,
        ):
            deps = create_stock_analysis_workflow_dependencies(tmp_path / "data.db")
            result = deps.company_quality_context_builder_factory()

        assert result is sentinel
        mock_ctor.assert_called_once_with(
            config_path=self.CUSTOM_PATHS.company_quality_context,
            scoring=None,
            neutral_score=50.0,
        )

    # --- explicit override wins ---

    def test_ticker_profile_explicit_override_wins(self, tmp_path):
        app_cfg = self._make_custom_app_config()
        sentinel = MagicMock()
        explicit_profile = "override/ticker.yaml"
        explicit_universes = "override/universes.yaml"

        with (
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".load_app_config",
                return_value=app_cfg,
            ),
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".create_ticker_profile_classifier",
                return_value=sentinel,
            ) as mock_ctor,
        ):
            deps = create_stock_analysis_workflow_dependencies(tmp_path / "data.db")
            result = deps.ticker_profile_classifier_factory(
                profile_path=explicit_profile,
                universes_path=explicit_universes,
            )

        assert result is sentinel
        mock_ctor.assert_called_once_with(
            profile_path=explicit_profile,
            universes_path=explicit_universes,
        )

    def test_institutional_accumulation_explicit_override_wins(self, tmp_path):
        app_cfg = self._make_custom_app_config()
        sentinel = MagicMock()
        explicit_path = "override/inst_accum.yaml"

        with (
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".load_app_config",
                return_value=app_cfg,
            ),
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".load_institutional_accumulation_config",
                return_value=sentinel,
            ) as mock_ctor,
        ):
            deps = create_stock_analysis_workflow_dependencies(tmp_path / "data.db")
            result = deps.institutional_accumulation_config_factory(
                path=explicit_path,
            )

        assert result is sentinel
        mock_ctor.assert_called_once_with(path=explicit_path)

    def test_company_quality_explicit_override_wins(self, tmp_path):
        app_cfg = self._make_custom_app_config()
        sentinel = MagicMock()
        explicit_path = "override/company_quality.yaml"

        with (
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".load_app_config",
                return_value=app_cfg,
            ),
            patch(
                "src.adapters.cli.stock_analysis_workflow_dependencies"
                ".create_company_quality_context_evidence_builder",
                return_value=sentinel,
            ) as mock_ctor,
        ):
            deps = create_stock_analysis_workflow_dependencies(tmp_path / "data.db")
            result = deps.company_quality_context_builder_factory(
                config_path=explicit_path,
            )

        assert result is sentinel
        mock_ctor.assert_called_once_with(
            config_path=explicit_path,
            scoring=None,
            neutral_score=50.0,
        )
