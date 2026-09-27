"""ActivationRoute Sys1 Decision Recipe.

Evaluates whether an initial user request requires the protocol or can bypass.
"""

from __future__ import annotations

from typing import Any

from pdl_taskmaster.providers.sys1.gating import evaluate_confidence_gate
from pdl_taskmaster.providers.sys1.recipes.base import Sys1Recipe, as_decision_instruction
from pdl_taskmaster.providers.sys1.schema import RecipeResult, Sys1Question, Sys1Request


class ActivationRouteRecipe(Sys1Recipe):
    """Evaluates whether an initial user request requires the protocol or can bypass."""

    @property
    def name(self) -> str:
        return "activation-route"

    @property
    def min_confidence(self) -> float:
        return 0.85

    def build_request(self, state: dict[str, Any], **kwargs: Any) -> Sys1Request:
        request_text = state.get("request", "")
        instruction = as_decision_instruction(
            "Determine the correct routing for this user message: does it request substantive task work "
            "requiring protocol governance, discuss protocol operation, or bypass?"
        )
        criteria = {
            "APPLY_PROTOCOL": "The message requests substantive task work, analysis, problem solving, or deliverables.",
            "PROTOCOL_DISCUSSION": "The message asks questions about how the harness or protocol works without requesting substantive task work.",
            "BYPASS": "The message is a pure greeting, farewell, or meta-interaction requiring no substantive work.",
        }
        question = Sys1Question(
            instructions=instruction,
            criteria=criteria,
            choices=["APPLY_PROTOCOL", "PROTOCOL_DISCUSSION", "BYPASS"],
        )
        return Sys1Request(
            state={"request": request_text},
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
        return RecipeResult(
            status=status,
            verdict=choice,
            confidence=gating.confidence,
            margin=gating.margin,
            entropy=gating.entropy,
            passed_gating=gating.passed,
            probabilities=gating.probabilities,
            duration_ms=duration_ms,
            metadata=response_body.get("metadata", {}),
        )

    def map_to_wire(self, result: RecipeResult) -> dict[str, Any]:
        return {
            "route": result.verdict if result.passed_gating else "APPLY_PROTOCOL",
            "response": None,
        }
