"""Base Checker Protocol and Verification Verdict."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ProblemDomain(str, Enum):
    """Canonical domain identifier for substantive verification."""

    PARTITION_SUM_TRIPLES = "partition_sum_triples"
    EXACT_COVER = "exact_cover"
    SUBSET_SUM = "subset_sum"
    GENERAL = "general"

    @classmethod
    def from_string(cls, val: str | None) -> ProblemDomain | None:
        if not val:
            return None
        cleaned = val.strip().lower()
        for member in cls:
            if member.value == cleaned:
                return member
        return None


@dataclass(frozen=True)
class VerificationVerdict:
    """Outcome of mechanical substantive verification."""
    valid: bool
    diagnostic: Optional[str] = None
    provisional: bool = False
    details: Optional[dict[str, Any]] = None


class BaseChecker(ABC):
    """Abstract base class for all deterministic domain checkers (P2)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique domain identifier for this checker."""
        ...

    @abstractmethod
    def check(
        self,
        witness: dict[str, Any] | Any,
        constraints: dict[str, Any],
        *,
        body: str | None = None,
    ) -> VerificationVerdict:
        """Deterministically verify whether the witness satisfies all mathematical/domain constraints."""
        ...
