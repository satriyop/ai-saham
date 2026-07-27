"""Custom application-layer exceptions."""


class NoProductionSignalEvidenceError(ValueError):
    """Canonical signal assessment requires setup or flow evidence."""
