"""Fallback Checker for Unregistered Problem Classes (P4/P5).

When a request is classified as requiring verified execution but has no
specialized domain checker registered, the fallback checker ensures the
presence of a witness and marks the result as 'provisional' rather than
silently passing it through as verified.
"""

from __future__ import annotations

from typing import Any

from pdl_taskmaster.verification.checkers.base import BaseChecker, VerificationVerdict


class FallbackChecker(BaseChecker):
    """Fallback checker that labels outputs provisional."""

    @property
    def name(self) -> str:
        return "fallback"

    def check(
        self,
        witness: dict[str, Any] | Any,
        constraints: dict[str, Any],
        *,
        body: str | None = None,
    ) -> VerificationVerdict:
        if witness is None:
            return VerificationVerdict(
                valid=False,
                diagnostic="Missing witness in Result IR for task requiring verified execution.",
            )

        if hasattr(witness, "model_dump"):
            w_dict = witness.model_dump()
        elif isinstance(witness, dict):
            w_dict = witness
        else:
            return VerificationVerdict(
                valid=False,
                diagnostic=f"Witness must be an object, got {type(witness).__name__}.",
            )

        polarity = w_dict.get("polarity")
        if polarity == "positive":
            data = w_dict.get("data")
            if not isinstance(data, dict) or not data:
                return VerificationVerdict(
                    valid=False,
                    diagnostic="Positive witness must contain non-empty 'data' dictionary.",
                )
            return VerificationVerdict(
                valid=True,
                provisional=True,
                diagnostic="Provisional result: domain-specific checker not registered for this problem class.",
                details={"polarity": "positive", "data_keys": list(data.keys())},
            )
        elif polarity == "negative":
            search_exhausted = w_dict.get("search_exhausted")
            if search_exhausted is not True:
                return VerificationVerdict(
                    valid=False,
                    diagnostic="Negative witness search_exhausted must be True to claim non-existence.",
                )
            return VerificationVerdict(
                valid=True,
                provisional=True,
                diagnostic="Provisional result: negative search claim not mechanically verified by domain checker.",
                details={"polarity": "negative", "search_exhausted": True},
            )

        return VerificationVerdict(
            valid=False,
            diagnostic=f"Unknown witness polarity: {polarity!r}.",
        )
