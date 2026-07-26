"""
Formula storage for persisting custom indicator formulas.

Stores formulas in YAML format at config/formulas.yaml for:
- Cross-session persistence
- Human-readable/editable format
- Git-friendly storage

Layer: Infrastructure
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator

import yaml

from src.application.dto.stored_formula import StoredFormula
from src.application.ports.formula_store import FormulaStoreError

logger = logging.getLogger(__name__)

# Default storage location
DEFAULT_FORMULAS_PATH = Path("config/formulas.yaml")


class FormulaStorage:
    """Persist custom formulas to YAML file.

    Handles saving, loading, and managing custom indicator formulas
    in a human-readable YAML format.

    Example:
        storage = FormulaStorage()
        storage.save("SMOOTH_RSI", "SMA(RSI(14), 10)", intent="smoothed RSI")
        formulas = storage.load_all()
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialize storage with optional custom path.

        Args:
            path: Custom path for formulas file. If None, uses
                  config/formulas.yaml.
        """
        self._path = path or DEFAULT_FORMULAS_PATH

    @property
    def path(self) -> Path:
        """Return the storage file path."""
        return self._path

    def save(
        self,
        name: str,
        formula: str,
        intent: str | None = None,
    ) -> StoredFormula:
        """Save a formula to persistent storage.

        Creates the parent directory if it doesn't exist.
        Overwrites existing formula with same name.

        Args:
            name: Formula name (will be uppercased).
            formula: Formula expression string.
            intent: Original natural language intent (optional).

        Returns:
            StoredFormula with metadata.

        Raises:
            FormulaStoreError: If storage operation fails.
        """
        name_upper = name.upper()
        now = datetime.now()

        try:
            # Ensure directory exists
            self._path.parent.mkdir(parents=True, exist_ok=True)

            # Load existing data
            data = self._load_raw()

            # Add/update formula
            data["formulas"][name_upper] = {
                "formula": formula,
                "intent": intent,
                "created": now.isoformat(),
            }

            # Write back
            self._save_raw(data)

            logger.info(f"Saved formula: {name_upper}")
            return StoredFormula(
                name=name_upper,
                formula=formula,
                intent=intent,
                created=now,
            )

        except Exception as e:
            raise FormulaStoreError(f"Failed to save formula: {e}") from e

    def get(self, name: str) -> StoredFormula | None:
        """Get a single formula by name.

        Args:
            name: Formula name (case-insensitive).

        Returns:
            StoredFormula if found, None otherwise.
        """
        name_upper = name.upper()
        data = self._load_raw()

        formula_data = data["formulas"].get(name_upper)
        if formula_data is None:
            return None

        return self._to_stored_formula(name_upper, formula_data)

    def exists(self, name: str) -> bool:
        """Check if a formula exists in storage.

        Args:
            name: Formula name (case-insensitive).

        Returns:
            True if formula exists in storage.
        """
        name_upper = name.upper()
        data = self._load_raw()
        return name_upper in data["formulas"]

    def delete(self, name: str) -> bool:
        """Delete a formula from storage.

        Args:
            name: Formula name (case-insensitive).

        Returns:
            True if formula was deleted, False if not found.

        Raises:
            FormulaStoreError: If delete operation fails.
        """
        name_upper = name.upper()

        try:
            data = self._load_raw()

            if name_upper not in data["formulas"]:
                return False

            del data["formulas"][name_upper]
            self._save_raw(data)

            logger.info(f"Deleted formula: {name_upper}")
            return True

        except Exception as e:
            raise FormulaStoreError(f"Failed to delete formula: {e}") from e

    def load_all(self) -> dict[str, StoredFormula]:
        """Load all formulas from storage.

        Returns:
            Dict mapping formula names to StoredFormula objects.
        """
        data = self._load_raw()
        return {
            name: self._to_stored_formula(name, formula_data)
            for name, formula_data in data["formulas"].items()
        }

    def list_names(self) -> list[str]:
        """List all formula names in storage.

        Returns:
            Sorted list of formula names.
        """
        data = self._load_raw()
        return sorted(data["formulas"].keys())

    def __iter__(self) -> Iterator[StoredFormula]:
        """Iterate over all stored formulas."""
        for formula in self.load_all().values():
            yield formula

    def __len__(self) -> int:
        """Return number of stored formulas."""
        data = self._load_raw()
        return len(data["formulas"])

    def _load_raw(self) -> dict:
        """Load raw YAML data from file.

        Returns empty structure if file doesn't exist.
        """
        if not self._path.exists():
            return {"formulas": {}}

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Handle empty file or invalid content
            if data is None:
                return {"formulas": {}}

            # Ensure formulas key exists
            if "formulas" not in data:
                data["formulas"] = {}

            return data

        except yaml.YAMLError as e:
            logger.warning(f"Invalid YAML in {self._path}: {e}")
            return {"formulas": {}}

    def _save_raw(self, data: dict) -> None:
        """Save raw YAML data to file."""
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=True,
            )

    def _to_stored_formula(self, name: str, data: dict) -> StoredFormula:
        """Convert raw dict to StoredFormula."""
        created_str = data.get("created")
        if created_str:
            try:
                created = datetime.fromisoformat(created_str)
            except ValueError:
                created = datetime.now()
        else:
            created = datetime.now()

        return StoredFormula(
            name=name,
            formula=data.get("formula", ""),
            intent=data.get("intent"),
            created=created,
        )
