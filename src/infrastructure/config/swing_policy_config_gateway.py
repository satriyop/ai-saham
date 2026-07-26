"""Source-controlled YAML gateway for guarded swing policy application."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from src.application.services.swing_tuning_config_paths import (
    parse_tuning_config_path,
)
from src.application.use_case.swing_policy_learning_use_case import (
    SwingPolicySnapshot,
)
from src.domain.value_objects.learning_artifacts import (
    LearningContractError,
    artifact_digest,
)

_DEFAULT_POLICY_FILES = (
    "config/signal_engine.yaml",
    "config/risk_engine.yaml",
    "config/swing_setups.yaml",
    "config/market_context_engine.yaml",
    "config/swing_targets.yaml",
    "config/swing_backtest.yaml",
)


def _default_dirty_checker(root: Path, relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", relative_path],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode != 0 or bool(result.stdout.strip())


class YamlSwingPolicyConfigGateway:
    def __init__(
        self,
        config_root: Path,
        *,
        policy_files: tuple[str, ...] = _DEFAULT_POLICY_FILES,
        dirty_checker: Callable[[Path, str], bool] = _default_dirty_checker,
    ) -> None:
        self._root = config_root.resolve()
        self._policy_files = policy_files
        self._dirty_checker = dirty_checker

    def read_snapshot(self) -> SwingPolicySnapshot:
        values: dict[str, Any] = {}
        documents: dict[str, Any] = {}
        for relative_path in self._policy_files:
            document = self._read(relative_path)
            documents[relative_path] = document
            self._flatten(relative_path, "", document, values)
        return SwingPolicySnapshot(
            config_hash=artifact_digest(documents),
            values=values,
        )

    def target_files_clean(self, changes: Mapping[str, Any]) -> bool:
        files = {parse_tuning_config_path(path).file_path for path in changes}
        return all(not self._dirty_checker(self._root, file_path) for file_path in files)

    def apply_changes(self, changes: Mapping[str, Any]) -> None:
        if not changes:
            raise LearningContractError("policy application changes must be non-empty")
        documents: dict[str, dict[str, Any]] = {}
        for target in changes:
            parsed = parse_tuning_config_path(target)
            if parsed.file_path not in self._policy_files:
                raise LearningContractError(
                    f"policy target file is not allowlisted: {parsed.file_path}"
                )
            if "*" in parsed.document_path:
                raise LearningContractError("wildcard policy targets cannot be applied")
            documents.setdefault(parsed.file_path, self._read(parsed.file_path))
            self._require_existing_path(
                documents[parsed.file_path], parsed.document_path
            )
        for target, value in changes.items():
            parsed = parse_tuning_config_path(target)
            self._assign(documents[parsed.file_path], parsed.document_path, value)
        for relative_path, document in documents.items():
            path = self._resolve(relative_path)
            with path.open("w", encoding="utf-8") as stream:
                yaml.safe_dump(
                    document,
                    stream,
                    sort_keys=False,
                    default_flow_style=False,
                    allow_unicode=True,
                )

    def _resolve(self, relative_path: str) -> Path:
        path = (self._root / relative_path).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise LearningContractError("policy target escapes config root") from exc
        return path

    def _read(self, relative_path: str) -> dict[str, Any]:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise LearningContractError(f"policy YAML does not exist: {relative_path}")
        with path.open(encoding="utf-8") as stream:
            document = yaml.safe_load(stream) or {}
        if not isinstance(document, dict):
            raise LearningContractError(f"policy YAML must be a mapping: {relative_path}")
        return document

    @classmethod
    def _flatten(
        cls,
        file_path: str,
        prefix: str,
        value: Any,
        output: dict[str, Any],
    ) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                next_prefix = f"{prefix}.{key}" if prefix else str(key)
                cls._flatten(file_path, next_prefix, child, output)
            return
        output[f"{file_path}:{prefix}"] = value

    @staticmethod
    def _require_existing_path(document: dict[str, Any], dotted_path: str) -> None:
        current: Any = document
        for segment in dotted_path.split("."):
            if not isinstance(current, dict) or segment not in current:
                raise LearningContractError(
                    f"policy document path does not exist: {dotted_path}"
                )
            current = current[segment]

    @staticmethod
    def _assign(document: dict[str, Any], dotted_path: str, value: Any) -> None:
        segments = dotted_path.split(".")
        current = document
        for segment in segments[:-1]:
            child = current[segment]
            assert isinstance(child, dict)
            current = child
        current[segments[-1]] = value
