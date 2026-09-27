"""Output Verifier Dispatcher (P2/P3).

Deterministic mechanical verifier that routes candidate witnesses to appropriate
domain checkers without model self-grading.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pdl_taskmaster.verification.checkers.base import BaseChecker, VerificationVerdict
from pdl_taskmaster.verification.checkers.fallback import FallbackChecker
from pdl_taskmaster.verification.checkers.partition_sum_triples import (
    PartitionSumTriplesChecker,
)


class OutputVerifier:
    """Mechanical verifier registry and dispatcher."""

    def __init__(self) -> None:
        self._checkers: dict[str, BaseChecker] = {}
        self._fallback = FallbackChecker()

        # Register default checkers
        self.register(PartitionSumTriplesChecker())

    def register(self, checker: BaseChecker) -> None:
        """Register a domain-specific checker."""
        self._checkers[checker.name] = checker

    def get_checker(self, domain: str | None) -> BaseChecker:
        """Retrieve the checker for a given domain, or fallback if unregistered."""
        if domain and domain in self._checkers:
            return self._checkers[domain]
        return self._fallback

    def detect_domain(self, context_or_text: str | dict[str, Any] | None) -> str | None:
        """Infer domain checker from context or problem text."""
        if not context_or_text:
            return None

        if isinstance(context_or_text, dict):
            # Check explicit domain field
            if "domain" in context_or_text:
                return str(context_or_text["domain"])
            # Check constraints or text
            text = " ".join(str(v) for v in context_or_text.values())
        else:
            text = str(context_or_text)

        if re.search(r"(?i)\b(?:schur\s+triples?|partition\b[^.\n]*\btriples?|sum\s+triples?)\b", text):
            return "partition_sum_triples"

        return None

    def check(
        self,
        witness: dict[str, Any] | Any,
        constraints: dict[str, Any] | None = None,
        *,
        domain: str | None = None,
        body: str | None = None,
    ) -> VerificationVerdict:
        """Check the witness using the appropriate domain checker."""
        effective_constraints = constraints or {}
        resolved_domain = domain or self.detect_domain(effective_constraints)
        if not resolved_domain and body:
            resolved_domain = self.detect_domain(body)

        checker = self.get_checker(resolved_domain)
        return checker.check(witness, effective_constraints, body=body)
