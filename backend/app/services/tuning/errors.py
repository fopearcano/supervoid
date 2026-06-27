"""Typed errors for the fine-tuning pipeline (Prompt 18)."""
from __future__ import annotations


class TuningError(Exception):
    """Base class for fine-tuning pipeline errors."""


class TuningExclusion(TuningError):
    """A candidate was rejected by the sanitiser's exclusion rules."""

    def __init__(self, reasons: list[str]):
        self.reasons = list(reasons or [])
        super().__init__("Excluded: " + ", ".join(self.reasons))


class TuningDeployBlocked(TuningError):
    """An adapter cannot be deployed because the deploy gate is not satisfied."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)
