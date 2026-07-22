"""Lazy cached-only composition for Research Corpus Health.

Layer: Adapter composition root
"""

from __future__ import annotations

from threading import Lock

from src.adapters.tui.controllers.research_health_controller import (
    ResearchHealthLoader,
)
from src.application.use_case.report_signal_readiness_use_case import (
    ReportSignalReadinessRequest,
    ReportSignalReadinessUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)


class _SerializedReadinessCapability:
    def __init__(self) -> None:
        self._use_case: ReportSignalReadinessUseCase | None = None
        self._lock = Lock()

    def __call__(self, target: str, cohort: str | None):
        with self._lock:
            if self._use_case is None:
                config = load_app_config()
                db_path = config.storage.db_path
                self._use_case = ReportSignalReadinessUseCase(
                    candidate_observations_repository=(
                        SQLiteCandidateObservationsRepository(db_path)
                    ),
                    signal_forward_labels_repository=(SQLiteSignalForwardLabelsRepository(db_path)),
                )
            return self._use_case.execute(
                ReportSignalReadinessRequest(
                    target=target,
                    semantic_compatibility_id=cohort,
                )
            )


def create_readiness_capability() -> ResearchHealthLoader:
    return _SerializedReadinessCapability()
