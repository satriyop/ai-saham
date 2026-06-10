"""
Annotation reader for .skill.yaml sidecar files.

Reads and validates skill annotations from sidecar YAML files.
Gracefully handles missing files (returns None, never raises).

Layer: Infrastructure
"""

import logging
from pathlib import Path

import yaml

from src.domain.value_objects.skill_annotation import SkillAnnotation

logger = logging.getLogger(__name__)

# Known annotation keys (for warning on unknown keys)
_KNOWN_KEYS = {"description", "when_to_use", "tags", "limitations", "examples"}
_REQUIRED_KEYS = {"description", "when_to_use"}


class AnnotationSchemaError(Exception):
    """Raised when a .skill.yaml file has invalid schema."""


class AnnotationReader:
    """Reads and validates .skill.yaml sidecar files."""

    def read(self, path: Path) -> SkillAnnotation | None:
        """Read a single-artifact .skill.yaml file.

        Args:
            path: Path to the .skill.yaml file.

        Returns:
            Parsed SkillAnnotation, or None if the file does not exist.

        Raises:
            AnnotationSchemaError: If the file exists but has invalid schema.
        """
        if not path.exists():
            return None

        data = self._load_yaml(path)
        if data is None:
            return None

        if not isinstance(data, dict):
            raise AnnotationSchemaError(
                f"Expected a mapping in {path}, got {type(data).__name__}"
            )

        self._warn_unknown_keys(data, path)
        return self._parse_annotation(data, path)

    def read_formula_annotations(
        self, path: Path
    ) -> dict[str, SkillAnnotation]:
        """Read a multi-formula .skill.yaml file (keyed by formula name).

        Args:
            path: Path to formulas.skill.yaml.

        Returns:
            Dict mapping formula name to its annotation.

        Raises:
            AnnotationSchemaError: If the file exists but has invalid schema.
        """
        if not path.exists():
            return {}

        data = self._load_yaml(path)
        if data is None:
            return {}

        if not isinstance(data, dict):
            raise AnnotationSchemaError(
                f"Expected a mapping in {path}, got {type(data).__name__}"
            )

        result: dict[str, SkillAnnotation] = {}
        for formula_name, formula_data in data.items():
            if not isinstance(formula_data, dict):
                logger.warning(
                    "Skipping formula '%s' in %s: expected mapping, got %s",
                    formula_name,
                    path,
                    type(formula_data).__name__,
                )
                continue
            try:
                result[formula_name] = self._parse_annotation(formula_data, path)
            except AnnotationSchemaError as e:
                logger.warning(
                    "Skipping formula '%s' in %s: %s", formula_name, path, e
                )

        return result

    def _load_yaml(self, path: Path) -> dict | None:
        """Load and parse a YAML file.

        Args:
            path: Path to YAML file.

        Returns:
            Parsed YAML data, or None on parse failure.

        Raises:
            AnnotationSchemaError: On YAML syntax errors.
        """
        try:
            text = path.read_text(encoding="utf-8")
            return yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise AnnotationSchemaError(f"Invalid YAML in {path}: {e}") from e
        except OSError as e:
            logger.warning("Could not read %s: %s", path, e)
            return None

    def _parse_annotation(
        self, data: dict, source_path: Path
    ) -> SkillAnnotation:
        """Parse a dict into a SkillAnnotation.

        Args:
            data: Parsed YAML dict.
            source_path: Path for error messages.

        Returns:
            Validated SkillAnnotation.

        Raises:
            AnnotationSchemaError: If required fields are missing or invalid.
        """
        # Check required fields
        missing = _REQUIRED_KEYS - set(data.keys())
        if missing:
            raise AnnotationSchemaError(
                f"Missing required fields in {source_path}: {', '.join(sorted(missing))}"
            )

        description = data.get("description", "")
        when_to_use = data.get("when_to_use", "")

        if not isinstance(description, str) or not description.strip():
            raise AnnotationSchemaError(
                f"'description' must be a non-empty string in {source_path}"
            )
        if not isinstance(when_to_use, str) or not when_to_use.strip():
            raise AnnotationSchemaError(
                f"'when_to_use' must be a non-empty string in {source_path}"
            )

        tags = self._to_str_tuple(data.get("tags", []), "tags", source_path)
        limitations = self._to_str_tuple(
            data.get("limitations", []), "limitations", source_path
        )
        examples = self._to_str_tuple(
            data.get("examples", []), "examples", source_path
        )

        return SkillAnnotation(
            description=description.strip(),
            when_to_use=when_to_use.strip(),
            tags=tags,
            limitations=limitations,
            examples=examples,
        )

    def _to_str_tuple(
        self, value: object, field_name: str, source_path: Path
    ) -> tuple[str, ...]:
        """Convert a YAML value to a tuple of strings.

        Args:
            value: Raw YAML value (should be a list of strings).
            field_name: Field name for error messages.
            source_path: Path for error messages.

        Returns:
            Tuple of strings.
        """
        if value is None:
            return ()
        if not isinstance(value, list):
            logger.warning(
                "'%s' should be a list in %s, got %s",
                field_name,
                source_path,
                type(value).__name__,
            )
            return ()
        return tuple(str(item) for item in value)

    def _warn_unknown_keys(self, data: dict, source_path: Path) -> None:
        """Warn about unknown keys in the annotation."""
        unknown = set(data.keys()) - _KNOWN_KEYS
        if unknown:
            logger.warning(
                "Unknown keys in %s: %s", source_path, ", ".join(sorted(unknown))
            )
