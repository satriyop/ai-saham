"""
Macro calendar category-rule config — loaded from config/macro_calendar.yaml.

Missing config file falls back to deterministic in-code defaults. Malformed
category values fail loudly.

Layer: Infrastructure
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.domain.value_objects.macro_calendar_event import MacroEventCategory
from src.infrastructure.config.app_config import AppConfig, load_app_config


@dataclass(frozen=True)
class MacroCategoryRule:
    category: MacroEventCategory
    title_contains: tuple[str, ...]


@dataclass(frozen=True)
class MacroCalendarConfig:
    category_rules: tuple[MacroCategoryRule, ...]
    default_category: MacroEventCategory = MacroEventCategory.OTHER


class MacroCalendarConfigError(ValueError):
    """Raised when macro_calendar.yaml is present but invalid."""


def default_macro_calendar_config_path(config: AppConfig | None = None) -> Path:
    cfg = config or load_app_config()
    return Path(cfg.config_paths.macro_calendar)


_DEFAULT_RULES: tuple[MacroCategoryRule, ...] = (
    MacroCategoryRule(
        category=MacroEventCategory.BI_RATE,
        title_contains=(
            "BI Rate",
            "BI 7-Day",
            "Bank Indonesia Rate",
            "7-Day Reverse Repo",
            "BI-Rate",
        ),
    ),
    MacroCategoryRule(
        category=MacroEventCategory.INFLATION,
        title_contains=("CPI", "Inflation", "Core Inflation"),
    ),
    MacroCategoryRule(
        category=MacroEventCategory.GROWTH,
        title_contains=("GDP", "Industrial Production"),
    ),
    MacroCategoryRule(
        category=MacroEventCategory.TRADE,
        title_contains=("Trade Balance", "Trade Surplus", "Trade Deficit", "Exports ", "Imports "),
    ),
)

_DEFAULT_CONFIG = MacroCalendarConfig(
    category_rules=_DEFAULT_RULES,
    default_category=MacroEventCategory.OTHER,
)


def load_macro_calendar_config(path: Path | None = None) -> MacroCalendarConfig:
    """Load category rules. Missing file → defaults. Invalid content → error."""
    config_path = path or default_macro_calendar_config_path()
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return _DEFAULT_CONFIG
    except OSError:
        return _DEFAULT_CONFIG

    try:
        raw_rules = data.get("category_rules") or []
        rules: list[MacroCategoryRule] = []
        for item in raw_rules:
            if not isinstance(item, dict):
                raise MacroCalendarConfigError("category_rules entries must be mappings")
            cat_raw = str(item.get("category", "")).strip()
            try:
                category = MacroEventCategory(cat_raw)
            except ValueError as e:
                known = ", ".join(c.value for c in MacroEventCategory)
                raise MacroCalendarConfigError(
                    f"Unknown category {cat_raw!r}. Known: {known}"
                ) from e
            contains = item.get("title_contains") or []
            if not isinstance(contains, list) or not contains:
                raise MacroCalendarConfigError(
                    f"category {cat_raw!r} requires non-empty title_contains list"
                )
            phrases = tuple(str(p).strip() for p in contains if str(p).strip())
            if not phrases:
                raise MacroCalendarConfigError(
                    f"category {cat_raw!r} requires non-empty title_contains phrases"
                )
            rules.append(MacroCategoryRule(category=category, title_contains=phrases))

        default_raw = str(data.get("default_category", "other")).strip()
        try:
            default_category = MacroEventCategory(default_raw)
        except ValueError as e:
            raise MacroCalendarConfigError(f"Unknown default_category {default_raw!r}") from e

        if not rules:
            return MacroCalendarConfig(
                category_rules=_DEFAULT_RULES,
                default_category=default_category,
            )
        return MacroCalendarConfig(
            category_rules=tuple(rules),
            default_category=default_category,
        )
    except MacroCalendarConfigError:
        raise
    except Exception as e:
        raise MacroCalendarConfigError(f"Invalid macro_calendar config: {e}") from e


def normalize_macro_category(
    title: str,
    config: MacroCalendarConfig | None = None,
) -> MacroEventCategory:
    """First-match case-insensitive substring rules; never raises on unknown title."""
    cfg = config or _DEFAULT_CONFIG
    haystack = (title or "").casefold()
    if not haystack:
        return cfg.default_category
    for rule in cfg.category_rules:
        for phrase in rule.title_contains:
            if phrase.casefold() in haystack:
                return rule.category
    return cfg.default_category
