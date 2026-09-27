"""Base Checker Protocol and Verification Verdict."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


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
