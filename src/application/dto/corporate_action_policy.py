"""
Corporate action event-risk policy — application-owned config shape.

These frozen dataclasses are the contract between the infrastructure YAML
loader (src/infrastructure/config/corporate_action_policy_config.py, which
owns only parsing/validation) and AssessCorporateActionEventRiskUseCase
(which owns only the policy type and its resolution behavior). Application
must not depend on infrastructure, so this type lives here rather than in
the loader module.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.value_objects.corporate_action_event_risk import (
    CorporateActionEventRiskFlag,
    CorporateActionEventRiskSeverity,
)


class CorporateActionPolicyConfigError(Exception):
    """Raised when corporate_action_policy.yaml is malformed or invalid."""


@dataclass(frozen=True)
class CorporateActionDateRolePolicy:
    severity: CorporateActionEventRiskSeverity
    lookback_days: int
    lookahead_days: int
    flags: tuple[CorporateActionEventRiskFlag, ...]


@dataclass(frozen=True)
class CorporateActionEventTypePolicy:
    enabled: bool
    date_roles: dict[str, CorporateActionDateRolePolicy] = field(default_factory=dict)


@dataclass(frozen=True)
class CorporateActionPolicyConfig:
    default_lookback_days: int
    default_lookahead_days: int
    event_types: dict[str, CorporateActionEventTypePolicy] = field(default_factory=dict)

    def resolve(self, event_type: str, date_role: str) -> CorporateActionDateRolePolicy | None:
        """Return the configured policy for (event_type, date_role), or None
        when the event type is unconfigured/disabled or the date role is not
        configured for it."""
        event_policy = self.event_types.get(event_type)
        if event_policy is None or not event_policy.enabled:
            return None
        return event_policy.date_roles.get(date_role)

    def max_lookback_days(self) -> int:
        values = [
            date_role.lookback_days
            for event_policy in self.event_types.values()
            if event_policy.enabled
            for date_role in event_policy.date_roles.values()
        ]
        return max(values) if values else self.default_lookback_days

    def max_lookahead_days(self) -> int:
        values = [
            date_role.lookahead_days
            for event_policy in self.event_types.values()
            if event_policy.enabled
            for date_role in event_policy.date_roles.values()
        ]
        return max(values) if values else self.default_lookahead_days
