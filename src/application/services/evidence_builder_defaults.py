"""Default evidence-builder factories shared by candidate evidence builders.

Both ``AccumulationCandidateEvidenceBuilder`` and ``PlanSwingEvidenceBuilder``
accept optional context-builder factories; these normalizers supply the same
deterministic defaults when a caller passes ``None``.

Layer: Application (pure assembly defaults, no IO)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.application.services.company_quality_context_evidence_builder import (
        CompanyQualityContextEvidenceBuilder,
    )
    from src.application.services.institutional_accumulation_evidence_builder import (
        InstitutionalAccumulationEvidenceBuilder,
    )
    from src.application.services.institutional_flow_config import (
        InstitutionalAccumulationConfig,
    )
    from src.application.services.sector_context_evidence_builder import (
        SectorContextEvidenceBuilder,
    )
    from src.application.services.sector_macro_context_evidence_builder import (
        SectorMacroContextEvidenceBuilder,
    )


def normalize_sector_context_factory(
    builder_factory: "Callable[[], SectorContextEvidenceBuilder] | None",
) -> "Callable[[], SectorContextEvidenceBuilder]":
    if builder_factory is not None:
        return builder_factory

    def _build() -> "SectorContextEvidenceBuilder":
        from src.application.services.sector_context_evidence_builder import (
            SectorContextConfig,
            SectorContextEvidenceBuilder,
        )

        return SectorContextEvidenceBuilder(SectorContextConfig.from_mapping({}), {})

    return _build


def normalize_sector_macro_context_factory(
    builder_factory: "Callable[[], SectorMacroContextEvidenceBuilder] | None",
) -> "Callable[[], SectorMacroContextEvidenceBuilder]":
    if builder_factory is not None:
        return builder_factory

    def _build() -> "SectorMacroContextEvidenceBuilder":
        from src.application.services.sector_macro_context_evidence_builder import (
            SectorMacroContextConfig,
            SectorMacroContextEvidenceBuilder,
        )

        return SectorMacroContextEvidenceBuilder(
            SectorMacroContextConfig.from_mapping(
                {
                    "sector_macro_context": {
                        "factor_library": {
                            "_placeholder": {
                                "series": "MTF=F",
                                "thresholds": {
                                    "supportive_min": 0.05,
                                    "headwind_max": -0.05,
                                },
                            }
                        },
                        "sector_maps": {},
                    }
                }
            )
        )

    return _build


def normalize_institutional_accumulation_factory(
    config_factory: Callable[[], "InstitutionalAccumulationConfig"] | None,
) -> Callable[[], "InstitutionalAccumulationEvidenceBuilder"]:
    def _build() -> "InstitutionalAccumulationEvidenceBuilder":
        from src.application.services.institutional_accumulation_evidence_builder import (
            InstitutionalAccumulationEvidenceBuilder,
        )

        if config_factory is not None:
            return InstitutionalAccumulationEvidenceBuilder(config_factory())
        return InstitutionalAccumulationEvidenceBuilder()

    return _build


def normalize_company_quality_context_factory(
    builder_factory: Callable[[], "CompanyQualityContextEvidenceBuilder"] | None,
) -> Callable[[], "CompanyQualityContextEvidenceBuilder"]:
    if builder_factory is not None:
        return builder_factory

    def _build() -> "CompanyQualityContextEvidenceBuilder":
        from src.application.services.company_quality_context_evidence_builder import (
            CompanyQualityContextConfig,
            CompanyQualityContextEvidenceBuilder,
        )

        return CompanyQualityContextEvidenceBuilder(CompanyQualityContextConfig.from_mapping({}))

    return _build
