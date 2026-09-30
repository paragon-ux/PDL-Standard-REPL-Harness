"""Output Verifier Dispatcher (P2/P3).

Deterministic mechanical verifier that routes candidate witnesses to appropriate
domain checkers without model self-grading.
"""

from __future__ import annotations

from typing import Any, Optional

from pdl_taskmaster.verification.checkers.base import (
    BaseChecker,
    ProblemDomain,
    VerificationVerdict,
)
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

    def get_checker(self, domain: ProblemDomain | str | None) -> BaseChecker:
        """Retrieve the checker for a given domain, or fallback if unregistered."""
        domain_key = domain.value if isinstance(domain, ProblemDomain) else domain
        if domain_key and domain_key in self._checkers:
            return self._checkers[domain_key]
        return self._fallback

    def detect_domain(self, context_or_text: ProblemDomain | str | dict[str, Any] | None) -> str | None:
        """Infer domain checker from typed context or problem text without regex heuristics."""
        if not context_or_text:
            return None

        if isinstance(context_or_text, ProblemDomain):
            return context_or_text.value

        if isinstance(context_or_text, dict):
            # Check explicit domain field (Pydantic SSOT)
            domain_val = context_or_text.get("domain")
            if domain_val:
                return domain_val.value if isinstance(domain_val, ProblemDomain) else str(domain_val)
            text = " ".join(str(v) for v in context_or_text.values())
        else:
            text = str(context_or_text)

        # Direct domain match
        direct = ProblemDomain.from_string(text)
        if direct is not None:
            return direct.value

        # Standard domain signature detection via exact token containment
        text_lower = text.lower()
        if "schur" in text_lower or ("triples" in text_lower and any(w in text_lower for w in ("sum", "partition", "disjoint", "divide"))):
            return ProblemDomain.PARTITION_SUM_TRIPLES.value
        if "exact cover" in text_lower or "dlx" in text_lower:
            return ProblemDomain.EXACT_COVER.value
        if "subset sum" in text_lower:
            return ProblemDomain.SUBSET_SUM.value

        return None

    def check(
        self,
        witness: dict[str, Any] | Any,
        constraints: dict[str, Any] | None = None,
        *,
        domain: ProblemDomain | str | None = None,
        body: str | None = None,
    ) -> VerificationVerdict:
        """Check the witness using the appropriate domain checker."""
        effective_constraints = constraints or {}
        resolved_domain = None
        if domain is not None:
            resolved_domain = domain.value if isinstance(domain, ProblemDomain) else str(domain)
        if not resolved_domain:
            resolved_domain = self.detect_domain(effective_constraints)
        if not resolved_domain and body:
            resolved_domain = self.detect_domain(body)

        checker = self.get_checker(resolved_domain)
        return checker.check(witness, effective_constraints, body=body)
