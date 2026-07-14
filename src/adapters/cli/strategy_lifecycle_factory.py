"""
Dependency wiring for strategy lifecycle CLI commands.

Layer: Adapter

This module is allowed to import infrastructure directly; it is the
composition point for the strategy init/validate/list commands.
"""

from src.application.services.skill_generator import SkillGeneratorService
from src.application.services.strategy_loader import StrategyLoader
from src.application.use_case.create_strategy_package_use_case import (
    CreateStrategyPackageUseCase,
)
from src.infrastructure.composition.indicator_registry_factory import create_indicator_registry
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.persistence.strategy_package_file_writer import (
    StrategyPackageFileWriter,
)
from src.infrastructure.skill.annotation_reader import AnnotationReader
from src.infrastructure.skill.markdown_writer import MarkdownSkillWriter
from src.infrastructure.skill.rules_hasher import RulesHasher
from src.infrastructure.skill.yaml_strategy_document_reader import YamlStrategyDocumentReader


def create_strategy_loader() -> StrategyLoader:
    registry = create_indicator_registry()
    return StrategyLoader(rules_loader=RulesYamlLoader(), registry=registry)


def create_strategy_package_use_case() -> CreateStrategyPackageUseCase:
    return CreateStrategyPackageUseCase(writer=StrategyPackageFileWriter())


def create_skill_generator_service() -> SkillGeneratorService:
    return SkillGeneratorService(
        annotation_reader=AnnotationReader(),
        skill_writer=MarkdownSkillWriter(),
        rules_hasher=RulesHasher(),
        strategy_reader=YamlStrategyDocumentReader(),
    )
