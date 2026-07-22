from types import SimpleNamespace

from src.adapters.tui.readiness import composition

from .readiness_fixtures import COHORT_A, TARGET, readiness_report


def test_readiness_composition_is_lazy_serialized_and_preserves_request(monkeypatch):
    repositories = []
    requests = []
    constructions = 0
    report = readiness_report()

    monkeypatch.setattr(
        composition,
        "load_app_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(db_path="local.db")),
    )

    def repository(db_path):
        repositories.append(db_path)
        return object()

    monkeypatch.setattr(composition, "SQLiteCandidateObservationsRepository", repository)
    monkeypatch.setattr(composition, "SQLiteSignalForwardLabelsRepository", repository)

    class UseCase:
        def __init__(self, **kwargs):
            nonlocal constructions
            constructions += 1

        def execute(self, request):
            requests.append(request)
            return report

    monkeypatch.setattr(composition, "ReportSignalReadinessUseCase", UseCase)

    capability = composition._SerializedReadinessCapability()
    assert repositories == []
    assert capability(f" {TARGET} ", f" {COHORT_A} ") is report
    assert capability(TARGET, None) is report
    assert constructions == 1
    assert repositories == ["local.db", "local.db"]
    assert requests[0].target == f" {TARGET} "
    assert requests[0].semantic_compatibility_id == f" {COHORT_A} "
    assert requests[1].target == TARGET
    assert requests[1].semantic_compatibility_id is None
