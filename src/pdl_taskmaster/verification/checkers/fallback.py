"""Fallback Checker for Unregistered Problem Classes (P4/P5).

When a request is classified as requiring verified execution but has no
specialized domain checker registered, the fallback checker ensures the
presence of a witness and marks the result as 'provisional' rather than
silently passing it through as verified.
"""

from __future__ import annotations

from typing import Any
from pydantic import ValidationError

from pdl_taskmaster.runtime.wire_payloads import NegativeWitness, PositiveWitness
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
            try:
                PositiveWitness.model_validate(w_dict)
            except ValidationError as val_err:
                err_msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in val_err.errors())
                return VerificationVerdict(
                    valid=False,
                    diagnostic=f"Invalid positive witness structure: {err_msg}",
                )
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
            try:
                NegativeWitness.model_validate(w_dict)
            except ValidationError as val_err:
                err_msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in val_err.errors())
                return VerificationVerdict(
                    valid=False,
                    diagnostic=f"Invalid negative witness structure: {err_msg}",
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
