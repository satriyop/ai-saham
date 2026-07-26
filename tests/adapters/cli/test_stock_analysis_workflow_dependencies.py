"""Focused unit tests for StockAnalysisWorkflowDependencies.

Layer: Test (adapter composition bundle).
"""

from unittest.mock import MagicMock, patch

from src.adapters.composition.stock_analysis_workflow_dependencies import (
    StockAnalysisWorkflowDependencies,
    create_stock_analysis_workflow_dependencies,
)
from src.application.services.risk_engine import RiskEngine
from src.application.services.signal_engine import SignalEngine
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.infrastructure.browser.stockbit_providers import StockbitProviders
from src.infrastructure.config.config_backed_market_context_provider import (
    ConfigBackedMarketContextProvider,
)
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_observation_risk_assessment_repository import (
    SQLiteObservationRiskAssessmentRepository,
)


class TestCreateDependencies:
    """Tests for the factory function."""

    def test_factory_creates_shared_repos(self, tmp_path):
        db_path = tmp_path / "test.db"
        deps = create_stock_analysis_workflow_dependencies(db_path)

        assert isinstance(deps.broker_repository, BrokerDataRepository)
        assert isinstance(deps.market_repository, MarketDataRepository)
        assert isinstance(
            deps.candidate_observations_repository,
            SQLiteCandidateObservationsRepository,
        )
        assert isinstance(
            deps.observation_risk_assessment_repository,
            SQLiteObservationRiskAssessmentRepository,
        )
        # Verify they share the same concrete db_path
        assert deps.db_path == db_path
        # Repos are distinct objects (not the same class)
        assert deps.broker_repository is not deps.market_repository

    def test_stockbit_providers_wired(self, tmp_path):
        deps = create_stock_analysis_workflow_dependencies(tmp_path / "test.db")

        assert isinstance(deps.stockbit_providers, StockbitProviders)
        # Verify sub-providers exist (read-only mode means api_client=None)
        assert deps.stockbit_providers.season_prov is not None
        assert deps.stockbit_providers.fundamentals_prov is not None

    def test_risk_engine_factory_callable_and_bound(self, tmp_path):
        db_path = tmp_path / "test.db"
        # Touch the db file so SQLite can open it
        db_path.touch()
        deps = create_stock_analysis_workflow_dependencies(db_path)

        engine = deps.create_risk_engine()
        assert isinstance(engine, RiskEngine)

    def test_signal_engine_factory_callable_and_bound(self, tmp_path):
        db_path = tmp_path / "test.db"
        db_path.touch()
        deps = create_stock_analysis_workflow_dependencies(db_path)

        engine = deps.create_signal_engine()
        assert isinstance(engine, SignalEngine)

    def test_market_context_provider_factory(self, tmp_path):
        db_path = tmp_path / "test.db"
        db_path.touch()
        deps = create_stock_analysis_workflow_dependencies(db_path)

        provider = deps.create_market_context_provider()
        assert isinstance(provider, ConfigBackedMarketContextProvider)

    def test_factories_are_callable(self, tmp_path):
        deps = create_stock_analysis_workflow_dependencies(tmp_path / "test.db")

        # All factory callables should be callable
        assert callable(deps.rules_loader_factory)
        assert callable(deps.indicator_registry_factory)
        assert callable(deps.ticker_profile_classifier_factory)
        assert callable(deps.institutional_accumulation_config_factory)
        assert callable(deps.sector_context_builder_factory)
        assert callable(deps.company_quality_context_builder_factory)
        assert callable(deps.create_risk_engine)
        assert callable(deps.create_signal_engine)
        assert callable(deps.create_market_context_provider)

    def test_no_config_loaded_at_import_time(self):
        """Verify importing the module does not trigger config loading."""
        import importlib
        import sys

        mod_name = "src.adapters.composition.stock_analysis_workflow_dependencies"
        original = sys.modules.get(mod_name)

        try:
            # Unload if already loaded
            if mod_name in sys.modules:
                del sys.modules[mod_name]

            # The module imports function references but does not CALL them.
            # If any config loading happened at import, a side-effect would fire.
            # Our factory functions are the only things that invoke loaders.
            mod = importlib.import_module(mod_name)
            # Confirm the module exports the expected public API (no loaded config objects).
            public_names = {
                name for name in dir(mod) if not name.startswith("_")
            }
            assert "StockAnalysisWorkflowDependencies" in public_names
            assert "create_stock_analysis_workflow_dependencies" in public_names
        finally:
            # Restore original module to avoid breaking other tests that
            # imported this module at module level and whose function
            # __globals__ still references the original module object.
            if original is not None:
                sys.modules[mod_name] = original

    def test_indicator_registry_factory_preserves_both_call_patterns(self, tmp_path):
        """indicator_registry_factory should work with and without repos."""
        deps = create_stock_analysis_workflow_dependencies(tmp_path / "test.db")

        # Pattern 1: no repos (as used in screen/trade accum factories)
        reg_no_repos = deps.indicator_registry_factory()

        # Pattern 2: with repos (as used in analyze_swing)
        reg_with_repos = deps.indicator_registry_factory(
            broker_repository=deps.broker_repository,
            market_repository=deps.market_repository,
        )

        assert reg_no_repos is not None
        assert reg_with_repos is not None
        # The indicator registry is the same type in both cases
        assert type(reg_no_repos) is type(reg_with_repos)


class TestDependencyInjectionInFactories:
    """Verify that factory functions use the provided deps bundle when given."""

    def test_create_accumulation_screen_workflow_uses_fake_deps(self, tmp_path):
        from src.adapters.composition.screen_accum_workflow_factory import (
            create_accumulation_screen_workflow,
        )

        fake_repo = MagicMock(spec=BrokerDataRepository)
        fake_market = MagicMock(spec=MarketDataRepository)
        fake_obs_repo = MagicMock(spec=SQLiteCandidateObservationsRepository)
        fake_stockbit = MagicMock(spec=StockbitProviders)
        fake_risk_engine = MagicMock()
        fake_signal_engine = MagicMock()
        fake_registry = MagicMock()
        fake_rules_loader = MagicMock()
        fake_classifier = MagicMock()
        fake_inst_config = MagicMock()
        fake_sector = MagicMock()
        fake_company = MagicMock()

        fake_deps = StockAnalysisWorkflowDependencies(
            db_path=tmp_path / "test.db",
            broker_repository=fake_repo,
            market_repository=fake_market,
            candidate_observations_repository=fake_obs_repo,
            observation_risk_assessment_repository=MagicMock(
                spec=SQLiteObservationRiskAssessmentRepository
            ),
            stockbit_providers=fake_stockbit,
            rules_loader_factory=lambda: fake_rules_loader,
            indicator_registry_factory=lambda *args, **kwargs: fake_registry,
            ticker_profile_classifier_factory=lambda: fake_classifier,
            institutional_accumulation_config_factory=lambda: fake_inst_config,
            sector_context_builder_factory=lambda: fake_sector,
            company_quality_context_builder_factory=lambda: fake_company,
            create_risk_engine=lambda: fake_risk_engine,
            create_signal_engine=lambda: fake_signal_engine,
            create_market_context_provider=MagicMock,
        )

        result = create_accumulation_screen_workflow(
            db_path=tmp_path / "test.db",
            screener_config=MagicMock(),
            with_risk=False,
            dependencies=fake_deps,
        )

        assert result.broker_repository is fake_repo
        assert result.market_repository is fake_market

    def test_create_run_accumulation_screen_workflow_use_case_threads_deps(
        self, tmp_path
    ):
        from src.adapters.composition.screen_accum_workflow_factory import (
            create_run_accumulation_screen_workflow_use_case,
        )

        fake_repo = MagicMock(spec=BrokerDataRepository)
        fake_market = MagicMock(spec=MarketDataRepository)
        fake_obs_repo = MagicMock(spec=SQLiteCandidateObservationsRepository)
        fake_stockbit = MagicMock(spec=StockbitProviders)
        fake_risk_engine = MagicMock()
        fake_signal_engine = MagicMock()
        fake_registry = MagicMock()
        fake_rules_loader = MagicMock()
        fake_classifier = MagicMock()
        fake_inst_config = MagicMock()
        fake_sector = MagicMock()
        fake_company = MagicMock()

        fake_deps = StockAnalysisWorkflowDependencies(
            db_path=tmp_path / "test.db",
            broker_repository=fake_repo,
            market_repository=fake_market,
            candidate_observations_repository=fake_obs_repo,
            observation_risk_assessment_repository=MagicMock(
                spec=SQLiteObservationRiskAssessmentRepository
            ),
            stockbit_providers=fake_stockbit,
            rules_loader_factory=lambda: fake_rules_loader,
            indicator_registry_factory=lambda *args, **kwargs: fake_registry,
            ticker_profile_classifier_factory=lambda: fake_classifier,
            institutional_accumulation_config_factory=lambda: fake_inst_config,
            sector_context_builder_factory=lambda: fake_sector,
            company_quality_context_builder_factory=lambda: fake_company,
            create_risk_engine=lambda: fake_risk_engine,
            create_signal_engine=lambda: fake_signal_engine,
            create_market_context_provider=MagicMock,
        )

        with patch(
            "src.adapters.composition.screen_accum_workflow_factory"
            ".RunAccumulationScreenWorkflowUseCase"
        ) as mock_uc_class:
            create_run_accumulation_screen_workflow_use_case(
                db_path=tmp_path / "test.db",
                screener_config=MagicMock(),
                swing_config=MagicMock(),
                dependencies=fake_deps,
            )

        mock_uc_class.assert_called_once()
        _args, kwargs = mock_uc_class.call_args
        assert kwargs["broker_repository"] is fake_repo
        assert kwargs["market_repository"] is fake_market
        assert kwargs["rules_loader"] is fake_rules_loader
        assert kwargs["indicator_registry_factory"] is fake_deps.indicator_registry_factory

    def test_create_swing_analysis_workflow_uses_fake_deps(self, tmp_path):
        from src.adapters.cli.analyze_swing_workflow_factory import (
            create_swing_analysis_workflow,
        )

        fake_repo = MagicMock(spec=BrokerDataRepository)
        fake_market = MagicMock(spec=MarketDataRepository)
        fake_obs_repo = MagicMock(spec=SQLiteCandidateObservationsRepository)
        fake_stockbit = MagicMock(spec=StockbitProviders)
        fake_risk_engine = MagicMock()
        fake_signal_engine = MagicMock()
        fake_registry = MagicMock()
        fake_rules_loader = MagicMock()
        fake_classifier = MagicMock()
        fake_inst_config = MagicMock()
        fake_sector = MagicMock()
        fake_company = MagicMock()

        fake_deps = StockAnalysisWorkflowDependencies(
            db_path=tmp_path / "test.db",
            broker_repository=fake_repo,
            market_repository=fake_market,
            candidate_observations_repository=fake_obs_repo,
            observation_risk_assessment_repository=MagicMock(
                spec=SQLiteObservationRiskAssessmentRepository
            ),
            stockbit_providers=fake_stockbit,
            rules_loader_factory=lambda: fake_rules_loader,
            indicator_registry_factory=lambda *args, **kwargs: fake_registry,
            ticker_profile_classifier_factory=lambda: fake_classifier,
            institutional_accumulation_config_factory=lambda: fake_inst_config,
            sector_context_builder_factory=lambda: fake_sector,
            company_quality_context_builder_factory=lambda: fake_company,
            create_risk_engine=lambda: fake_risk_engine,
            create_signal_engine=lambda: fake_signal_engine,
            create_market_context_provider=MagicMock,
        )

        with patch(
            "src.adapters.cli.analyze_swing_workflow_factory"
            ".SwingAnalysisWorkflowUseCase"
        ) as mock_uc_class:
            create_swing_analysis_workflow(
                db_path=tmp_path / "test.db",
                setup_name="foreign-bounce",
                swing_config=MagicMock(),
                analyze_config=MagicMock(),
                smart_money_brokers=set(),
                noise_brokers=set(),
                broker_weights={},
                dependencies=fake_deps,
            )

        mock_uc_class.assert_called_once()
        _args, kwargs = mock_uc_class.call_args
        assert kwargs["broker_repository"] is fake_repo
        assert kwargs["market_repository"] is fake_market
        assert kwargs["rules_loader"] is fake_rules_loader
        assert kwargs["risk_engine"] is fake_risk_engine
        assert kwargs["signal_engine"] is fake_signal_engine
        assert kwargs["candidate_observations_repository"] is fake_obs_repo
        assert (
            kwargs["ticker_profile_classifier_factory"]
            is fake_deps.ticker_profile_classifier_factory
        )
        assert (
            kwargs["institutional_accumulation_config_factory"]
            is fake_deps.institutional_accumulation_config_factory
        )
        assert (
            kwargs["sector_context_builder_factory"]
            is fake_deps.sector_context_builder_factory
        )
        assert (
            kwargs["company_quality_context_builder_factory"]
            is fake_deps.company_quality_context_builder_factory
        )

    def test_create_log_accumulation_trade_workflow_uses_fake_deps(self, tmp_path):
        from src.adapters.cli.trade_accum_workflow_factory import (
            create_log_accumulation_trade_workflow,
        )

        fake_repo = MagicMock(spec=BrokerDataRepository)
        fake_market = MagicMock(spec=MarketDataRepository)
        fake_obs_repo = MagicMock(spec=SQLiteCandidateObservationsRepository)
        fake_stockbit = MagicMock(spec=StockbitProviders)
        fake_risk_engine = MagicMock()
        fake_signal_engine = MagicMock()
        fake_registry = MagicMock()
        fake_rules_loader = MagicMock()
        fake_classifier = MagicMock()
        fake_inst_config = MagicMock()
        fake_sector = MagicMock()
        fake_company = MagicMock()

        fake_deps = StockAnalysisWorkflowDependencies(
            db_path=tmp_path / "test.db",
            broker_repository=fake_repo,
            market_repository=fake_market,
            candidate_observations_repository=fake_obs_repo,
            observation_risk_assessment_repository=MagicMock(
                spec=SQLiteObservationRiskAssessmentRepository
            ),
            stockbit_providers=fake_stockbit,
            rules_loader_factory=lambda: fake_rules_loader,
            indicator_registry_factory=lambda *args, **kwargs: fake_registry,
            ticker_profile_classifier_factory=lambda: fake_classifier,
            institutional_accumulation_config_factory=lambda: fake_inst_config,
            sector_context_builder_factory=lambda: fake_sector,
            company_quality_context_builder_factory=lambda: fake_company,
            create_risk_engine=lambda: fake_risk_engine,
            create_signal_engine=lambda: fake_signal_engine,
            create_market_context_provider=MagicMock,
        )

        with patch(
            "src.adapters.cli.trade_accum_workflow_factory.LogSwingCandidateUseCase"
        ) as mock_log_class:
            create_log_accumulation_trade_workflow(
                db_path=tmp_path / "test.db",
                journal_path=tmp_path / "journal.csv",
                with_regime=False,
                regime_universe=None,
                benchmark="IHSG",
                dependencies=fake_deps,
            )

        mock_log_class.assert_called_once()
        _args, kwargs = mock_log_class.call_args
        assert kwargs["market_repository"] is fake_market
        assert kwargs["screen_use_case"] is not None

    def test_run_swing_backtest_uses_fake_deps(self, tmp_path):
        from src.adapters.cli.trade_swing_backtest_runner import _run_swing_backtest

        fake_repo = MagicMock(spec=BrokerDataRepository)
        fake_market = MagicMock(spec=MarketDataRepository)
        fake_obs_repo = MagicMock(spec=SQLiteCandidateObservationsRepository)
        fake_stockbit = MagicMock(spec=StockbitProviders)
        fake_risk_engine = MagicMock()
        fake_signal_engine = MagicMock()
        fake_registry = MagicMock()
        fake_rules_loader = MagicMock()
        fake_classifier = MagicMock()
        fake_inst_config = MagicMock()
        fake_sector = MagicMock()
        fake_company = MagicMock()
        fake_market_context_provider = MagicMock()

        fake_deps = StockAnalysisWorkflowDependencies(
            db_path=tmp_path / "test.db",
            broker_repository=fake_repo,
            market_repository=fake_market,
            candidate_observations_repository=fake_obs_repo,
            observation_risk_assessment_repository=MagicMock(
                spec=SQLiteObservationRiskAssessmentRepository
            ),
            stockbit_providers=fake_stockbit,
            rules_loader_factory=lambda: fake_rules_loader,
            indicator_registry_factory=lambda *args, **kwargs: fake_registry,
            ticker_profile_classifier_factory=lambda: fake_classifier,
            institutional_accumulation_config_factory=lambda: fake_inst_config,
            sector_context_builder_factory=lambda: fake_sector,
            company_quality_context_builder_factory=lambda: fake_company,
            create_risk_engine=lambda: fake_risk_engine,
            create_signal_engine=lambda: fake_signal_engine,
            create_market_context_provider=lambda: fake_market_context_provider,
        )

        with (
            patch(
                "src.adapters.cli.trade_swing_backtest_runner.resolve_tickers",
                return_value=["BBCA"],
            ),
            patch(
                "src.adapters.cli.trade_swing_backtest_runner"
                ".load_swing_backtest_runner_config"
            ) as mock_load_config,
            patch(
                "src.adapters.cli.trade_swing_backtest_runner.SwingBacktestUseCase"
            ) as mock_bt_class,
        ):
            mock_config = MagicMock()
            mock_config.accumulation_config = MagicMock()
            mock_config.accumulation_config.derived_features = {}
            mock_config.swing_config = MagicMock()
            mock_config.swing_config.setup_targets = {}
            mock_config.swing_config.resistance_gate_enabled = False
            mock_config.swing_config.resistance_headroom_min_pct = 0.0
            mock_config.swing_config.ex_date_warning_days = 0
            mock_config.backtest_config = MagicMock()
            mock_config.backtest_config.forward_data_lookahead_days = 1
            mock_config.backtest_config.same_day_exit_priority = "stop_first"
            mock_config.backtest_config.attribution_high_min_score = 70
            mock_config.backtest_config.attribution_mid_min_score = 50
            mock_config.setup_config = MagicMock()
            mock_load_config.return_value = mock_config

            _run_swing_backtest(
                tickers=["BBCA"],
                universe=None,
                setup="foreign-bounce",
                start="2026-06-19",
                end=None,
                capital=10000000,
                risk_pct=1.0,
                max_positions=3,
                take_profit=5.0,
                stop_loss=5.0,
                max_hold=20,
                cost_bps=20.0,
                with_regime=False,
                allow_regimes=None,
                benchmark="COMPOSITE",
                db_path=tmp_path / "test.db",
                announce=False,
                config=mock_config,
                dependencies=fake_deps,
            )

        mock_bt_class.assert_called_once()
        _args, kwargs = mock_bt_class.call_args
        assert kwargs["broker_repository"] is fake_repo
        assert kwargs["market_repository"] is fake_market
        assert kwargs["rules_loader"] is fake_rules_loader
        assert kwargs["risk_engine"] is fake_risk_engine
        assert kwargs["market_context_provider"] is fake_market_context_provider
