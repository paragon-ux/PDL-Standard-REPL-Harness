"""ActivationRoute Sys1 Decision Recipe (ADR-0020).

Evaluates whether an initial user request requires the protocol, can bypass,
discusses protocol operation, or must be immediately refused due to environmental,
scope, or policy boundaries.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

from pdl_taskmaster.providers.sys1.gating import evaluate_confidence_gate
from pdl_taskmaster.providers.sys1.recipes.base import Sys1Recipe, as_decision_instruction
from pdl_taskmaster.providers.sys1.schema import RecipeResult, Sys1Question, Sys1Request

# Deterministic patterns for environment/policy boundary enforcement
_MEDICAL_PATTERNS = re.compile(
    r"(?i)\b(?:diagnos[ei]|prescri(?:be|ption)|dosage|medications?|medical\s+advice|cure\s+for)\b"
)

_NETWORK_PATTERNS = re.compile(
    r"(?i)\b(?:fetch\s+(?:from\s+)?https?://|scrape\s+(?:the\s+)?website|"
    r"download\s+from\s+https?://|connect\s+to\s+live\s+api|http\s+get|curl\s+https?://)\b"
)

_KNOWLEDGE_FUTURE_PATTERNS = re.compile(
    r"(?i)\b(?:202[6-9]|20[3-9]\d)\s+(?:winners?|election|olympics|world\s+cup|award)\b"
)


class ActivationRouteRecipe(Sys1Recipe):
    """Evaluates whether an initial user request requires the protocol or can bypass."""

    @property
    def name(self) -> str:
        return "activation-route"

    @property
    def min_confidence(self) -> float:
        return 0.85

    @classmethod
    def classify_text_deterministic(
        cls,
        text: str,
        env: Optional[dict[str, Any]] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """Fast-path deterministic classifier based on environment bounds and policy signatures.

        Returns:
            (route, refusal_response) if a deterministic match occurs, else (None, None).
        """
        if not text:
            return None, None

        env_dict = env or {}
        policy_scope = env_dict.get("policy_scope") or os.environ.get("PDLT_POLICY_SCOPE", "technical")
        sandbox_network = env_dict.get("sandbox_network") or os.environ.get("PDLT_SANDBOX_NETWORK", "false")
        knowledge_cutoff = env_dict.get("knowledge_cutoff") or os.environ.get("PDLT_KNOWLEDGE_CUTOFF", "2024-06")

        # 1. Out-of-scope medical/clinical requests
        if policy_scope == "technical" and _MEDICAL_PATTERNS.search(text):
            refusal = (
                "Medical diagnosis and medication recommendations are strictly out of scope "
                "for this technical assistant. Please consult a licensed healthcare professional."
            )
            return "BLOCKED_BY_HIGHER_PRIORITY", refusal

        # 2. External network requests when sandbox is offline
        if str(sandbox_network).lower() in ("false", "0", "no") and _NETWORK_PATTERNS.search(text):
            refusal = (
                "External network access, URL fetching, and live web scraping are disabled "
                "in this offline sandboxed execution environment."
            )
            return "BLOCKED_BY_HIGHER_PRIORITY", refusal

        # 3. Knowledge cutoff for future events without search
        if _KNOWLEDGE_FUTURE_PATTERNS.search(text):
            refusal = (
                f"The requested event postdates the knowledge cutoff date ({knowledge_cutoff}), "
                "and live external search is disabled in this environment."
            )
            return "BLOCKED_BY_HIGHER_PRIORITY", refusal

        return None, None

    def build_request(self, state: dict[str, Any], **kwargs: Any) -> Sys1Request:
        request_text = state.get("request", "")
        env = state.get("env") or {}
        sandbox_network = env.get("sandbox_network") or os.environ.get("PDLT_SANDBOX_NETWORK", "false")
        policy_scope = env.get("policy_scope") or os.environ.get("PDLT_POLICY_SCOPE", "technical")

        instruction = as_decision_instruction(
            "Determine the correct routing for this user message: does it request substantive technical work "
            "requiring protocol governance, discuss protocol operation, bypass, or must it be refused immediately "
            "due to environmental or policy bounds?"
        )
        criteria = {
            "APPLY_PROTOCOL": "The message requests substantive task work, analysis, problem solving, or deliverables within supported technical scope.",
            "PROTOCOL_DISCUSSION": "The message asks questions about how the harness or protocol works without requesting substantive task work.",
            "BYPASS": "The message is a pure greeting, farewell, or meta-interaction requiring no substantive work.",
            "BLOCKED_BY_HIGHER_PRIORITY": (
                "The message must be refused immediately because it requests medical/clinical diagnosis or medication "
                "dosages, requests external network access when network is disabled, or asks for post-cutoff events."
            ),
        }
        question = Sys1Question(
            instructions=instruction,
            criteria=criteria,
            choices=["APPLY_PROTOCOL", "PROTOCOL_DISCUSSION", "BYPASS", "BLOCKED_BY_HIGHER_PRIORITY"],
        )
        return Sys1Request(
            state={
                "request": request_text,
                "sandbox_network": sandbox_network,
                "policy_scope": policy_scope,
            },
            questions={"route": question},
        )

    def parse_response(
        self, response_body: dict[str, Any], *, duration_ms: float = 0.0
    ) -> RecipeResult:
        answers = response_body.get("answers", {})
        ans = answers.get("route", {})
        gating = evaluate_confidence_gate(ans, confidence_floor=self.min_confidence)
        choice = gating.choice or "APPLY_PROTOCOL"
        status = "ready" if gating.passed else "review"
        metadata = dict(response_body.get("metadata", {}))

        if choice == "BLOCKED_BY_HIGHER_PRIORITY":
            refusal_response = ans.get("response") or ans.get("refusal_response") or (
                "This request exceeds the supported policy and environmental scope boundaries of this system."
            )
            metadata["refusal_response"] = refusal_response

        return RecipeResult(
            status=status,
            verdict=choice,
            confidence=gating.confidence,
            margin=gating.margin,
            entropy=gating.entropy,
            passed_gating=gating.passed,
            probabilities=gating.probabilities,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def map_to_wire(self, result: RecipeResult) -> dict[str, Any]:
        route = result.verdict if result.passed_gating else "APPLY_PROTOCOL"
        response = None
        if route == "BLOCKED_BY_HIGHER_PRIORITY":
            response = (
                result.metadata.get("refusal_response")
                or "This request exceeds the supported policy and environmental scope boundaries of this system."
            )
        return {
            "route": route,
            "response": response,
        }
