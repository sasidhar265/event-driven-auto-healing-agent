"""Shared immutable values passed between runtime services."""

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Candidate:
    """A specialist agent's proposed remediation before governance is applied."""
    agent_type: str
    title: str
    rationale: str
    proposed_changes: dict[str, Any]
    base_confidence: float


@dataclass(frozen=True)
class FailureRoute:
    """Explainable result of classifying an incoming failure."""

    category: str
    confidence: float
    matched_signals: tuple[str, ...]
    alternatives: tuple[tuple[str, float], ...]
    ambiguous: bool = False
