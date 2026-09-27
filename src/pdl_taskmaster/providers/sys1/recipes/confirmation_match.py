"""ConfirmationMatch Sys1 Decision Recipe.

Evaluates whether user feedback clearly agrees to, rejects, or is unclear about a proposal.
"""

from __future__ import annotations

from typing import Any

from pdl_taskmaster.providers.sys1.gating import evaluate_confidence_gate
from pdl_taskmaster.providers.sys1.recipes.base import Sys1Recipe, as_decision_instruction
from pdl_taskmaster.providers.sys1.schema import RecipeResult, Sys1Question, Sys1Request


class ConfirmationMatchRecipe(Sys1Recipe):
    """Evaluates whether user feedback clearly agrees to, rejects, or is unclear about a proposal."""

    @property
    def name(self) -> str:
        return "confirmation-match"

    @property
    def min_confidence(self) -> float:
        return 0.80

    def build_request(self, state: dict[str, Any], **kwargs: Any) -> Sys1Request:
        proposal = state.get("proposal", "")
        response = state.get("response", "")
        instruction = as_decision_instruction(
            "Does response clearly agree to or reject this exact proposal? "
            "Do not treat politeness, acknowledgment, a question, or agreement to only part of the proposal as full agreement."
        )
        criteria = {
            "agrees": "The response clearly agrees to this complete proposal without conditions or requests for changes.",
            "rejects": "The response clearly rejects this proposal or asks to stop/cancel.",
            "unclear": "The response is conditional, partial, ambiguous, asks a question, or suggests modifications.",
        }
        question = Sys1Question(
            instructions=instruction,
            criteria=criteria,
            choices=["agrees", "rejects", "unclear"],
        )
        return Sys1Request(
            state={"proposal": proposal, "response": response},
            questions={"confirmation": question},
        )

    def parse_response(
        self, response_body: dict[str, Any], *, duration_ms: float = 0.0
    ) -> RecipeResult:
        answers = response_body.get("answers", {})
        ans = answers.get("confirmation", {})
        gating = evaluate_confidence_gate(ans, confidence_floor=self.min_confidence)
        choice = gating.choice or "unclear"
        status = "ready" if (gating.passed and choice in {"agrees", "rejects"}) else "review"
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
        if result.verdict == "agrees":
            return {
                "kind": "REVIEW_FACTS",
                "task_change_dimensions": [],
                "approach_change_dimensions": [],
                "progression_requested": True,
            }
        if result.verdict == "rejects":
            return {"kind": "CANCEL"}
        return {"kind": "UNRESOLVED"}
