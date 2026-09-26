"""TypeSafe Jev System 1 Native Decisions API Client & Multi-Dimensional Confidence Gating.

Implements ADR-0012:
- Sovereign internal routing: harness owns all state transitions.
- Direct invocation of OpenRouter / TypeSafe Decisions API (POST /api/alpha/decisions).
- Tripartite confidence gating:
    1. Calibrated confidence >= 0.85
    2. Top-2 margin >= 0.40
    3. Normalized Shannon entropy <= 0.35
- Deterministic fail-closed fallback ladder.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
import time
from typing import Any
import urllib.error
import urllib.request

CONFIDENCE_FLOOR: float = 0.85
MARGIN_FLOOR: float = 0.40
ENTROPY_CEIL: float = 0.35

DEFAULT_DECISIONS_URL: str = "https://openrouter.ai/api/alpha/decisions"


@dataclass(frozen=True)
class GatingResult:
    choice: str
    confidence: float
    margin: float
    entropy: float
    passed: bool
    probabilities: dict[str, float]


def evaluate_confidence_gate(answer: dict[str, Any]) -> GatingResult:
    """Evaluate ADR-0012 Tripartite Confidence Gate.

    Checks:
      1. Calibrated confidence >= 0.85
      2. Top-2 probability margin >= 0.40
      3. Normalized Shannon entropy <= 0.35
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

    passed = (confidence >= CONFIDENCE_FLOOR) and (margin >= MARGIN_FLOOR) and (norm_entropy <= ENTROPY_CEIL)
    return GatingResult(
        choice=choice,
        confidence=confidence,
        margin=margin,
        entropy=norm_entropy,
        passed=passed,
        probabilities=probs,
    )


def call_jev_decisions(
    *,
    state: str,
    questions: dict[str, Any],
    api_key: str,
    base_url: str = "https://openrouter.ai/api/v1",
    model: str = "typesafe/jev-1.13",
    timeout: float = 15.0,
) -> tuple[dict[str, Any], float]:
    """Call TypeSafe Jev via the native Decisions API endpoint."""
    if not api_key:
        raise ValueError("API key is required for Jev Decisions API")

    # Resolve decisions endpoint
    if "openrouter.ai" in base_url.lower():
        decisions_url = DEFAULT_DECISIONS_URL
    else:
        decisions_url = f"{base_url.rstrip('/')}/decisions"

    payload = {
        "model": model,
        "state": state,
        "questions": questions,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        decisions_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        duration = time.perf_counter() - t0
        body = json.loads(resp.read().decode("utf-8"))
        return body, duration


def build_activation_question() -> dict[str, Any]:
    """Question schema for INTERPRET_ACTIVATION."""
    return {
        "route": {
            "type": "choice",
            "instructions": (
                "Determine whether this request activates the confirmation protocol, discusses it, "
                "bypasses it as unconfirmed execution, or is blocked by safety."
            ),
            "choices": ["APPLY_PROTOCOL", "PROTOCOL_DISCUSSION", "BYPASS", "BLOCKED_BY_HIGHER_PRIORITY"],
            "criteria": {
                "APPLY_PROTOCOL": (
                    "User explicitly invokes confirm-with-pseudocode, requests a review before execution, "
                    "or asks for confirmation of request meaning."
                ),
                "PROTOCOL_DISCUSSION": "User asks questions about the protocol specification or harness mechanics.",
                "BYPASS": "Ordinary user request that does not invoke or request the confirmation protocol.",
                "BLOCKED_BY_HIGHER_PRIORITY": "Violates higher-priority constraints.",
            },
        }
    }


def build_review_question() -> dict[str, Any]:
    """Question schema for INTERPRET_PROMPT_REVIEW and INTERPRET_PLAN_REVIEW."""
    return {
        "progression_requested": {
            "type": "choice",
            "instructions": "Did the user explicitly confirm, accept, approve, or ask to proceed with execution?",
            "choices": ["YES", "NO"],
            "criteria": {
                "YES": "Positive confirmation: 'confirm', 'proceed', 'looks good', 'approved', 'yes'.",
                "NO": "User rejects, questions, modifies, or gives non-committal ambiguous feedback.",
            },
        },
        "revises_task": {
            "type": "choice",
            "instructions": "Does the user modify, revise, or add constraints to the substantive task definition?",
            "choices": ["YES", "NO"],
            "criteria": {
                "YES": "User changes goals, outputs, formats, libraries, requirements, or constraints.",
                "NO": "User accepts prompt as-is or makes no substantive changes.",
            },
        },
    }


def map_activation_result(resp_body: dict[str, Any]) -> dict[str, Any]:
    """Map Jev Decisions API response to ActivationDecisionPayload dict."""
    answers = resp_body.get("answers") or {}
    route_ans = answers.get("route") or {}
    gate = evaluate_confidence_gate(route_ans)

    if not gate.passed:
        # ADR-0012 Fail-closed: low-confidence activation defaults to APPLY_PROTOCOL
        return {"route": "APPLY_PROTOCOL", "confidence": min(gate.confidence, 0.50)}

    return {"route": gate.choice, "confidence": gate.confidence}


def map_review_result(resp_body: dict[str, Any]) -> dict[str, Any]:
    """Map Jev Decisions API response to ArtifactReviewPayload dict."""
    answers = resp_body.get("answers") or {}
    prog_gate = evaluate_confidence_gate(answers.get("progression_requested") or {})
    rev_gate = evaluate_confidence_gate(answers.get("revises_task") or {})

    # If confidence gating fails on either dimension, fail-closed to UNRESOLVED (REVIEW-09 Human Card)
    if not prog_gate.passed or not rev_gate.passed:
        return {"kind": "UNRESOLVED", "confidence": min(prog_gate.confidence, rev_gate.confidence, 0.50)}

    if rev_gate.choice == "YES":
        return {
            "kind": "REVIEW_FACTS",
            "task_change_dimensions": ["ACTION_SUBJECT_OR_OBJECT"],
            "approach_change_dimensions": [],
            "progression_requested": False,
            "confidence": rev_gate.confidence,
        }

    if prog_gate.choice == "YES":
        return {
            "kind": "REVIEW_FACTS",
            "task_change_dimensions": [],
            "approach_change_dimensions": [],
            "progression_requested": True,
            "confidence": prog_gate.confidence,
        }

    return {
        "kind": "SUBSTANTIVE_DISCUSSION",
        "confidence": prog_gate.confidence,
    }
