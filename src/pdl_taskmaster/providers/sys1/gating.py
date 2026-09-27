"""Tripartite Confidence Gating for Sys1 Decisions.

Implements ADR-0012:
1. Calibrated confidence floor (P_cal >= 0.85 by default)
2. Top-2 probability margin floor (Delta p >= 0.40)
3. Normalized Shannon entropy ceiling (H(p) <= 0.35)
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

DEFAULT_CONFIDENCE_FLOOR: float = 0.85
DEFAULT_MARGIN_FLOOR: float = 0.40
DEFAULT_ENTROPY_CEILING: float = 0.35


@dataclass(frozen=True)
class GatingResult:
    """Outcome of evaluating the tripartite confidence gate."""

    choice: str
    confidence: float
    margin: float
    entropy: float
    passed: bool
    probabilities: dict[str, float]


def evaluate_confidence_gate(
    answer: dict[str, Any],
    *,
    confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
    margin_floor: float = DEFAULT_MARGIN_FLOOR,
    entropy_ceiling: float = DEFAULT_ENTROPY_CEILING,
) -> GatingResult:
    """Evaluate the tripartite confidence gate against an answer dictionary.

    Args:
        answer: Dictionary containing at least:
            - "choice": Selected candidate label (str)
            - "confidence": Float in [0, 1]
            - "probabilities": Dict mapping candidate labels to float probabilities
        confidence_floor: Minimum required confidence (default 0.85)
        margin_floor: Minimum difference between top-1 and top-2 probabilities (default 0.40)
        entropy_ceiling: Maximum allowed normalized Shannon entropy (default 0.35)

    Returns:
        GatingResult with computed metrics and pass/fail verdict.
    """
    choice = str(answer.get("choice", "")).strip()
    confidence = float(answer.get("confidence", 0.0))
    probs = {str(k): float(v) for k, v in (answer.get("probabilities") or {}).items()}

    sorted_probs = sorted(probs.values(), reverse=True)
    p1 = sorted_probs[0] if len(sorted_probs) > 0 else confidence
    p2 = sorted_probs[1] if len(sorted_probs) > 1 else 0.0
    margin = p1 - p2

    k = max(len(probs), 2)
    entropy = 0.0
    for p in probs.values():
        if p > 0.0:
            entropy -= p * math.log(p)
    norm_entropy = entropy / math.log(k) if k > 1 else 0.0

    passed = (
        (confidence >= confidence_floor)
        and (margin >= margin_floor)
        and (norm_entropy <= entropy_ceiling)
    )

    return GatingResult(
        choice=choice,
        confidence=confidence,
        margin=margin,
        entropy=norm_entropy,
        passed=passed,
        probabilities=probs,
    )
