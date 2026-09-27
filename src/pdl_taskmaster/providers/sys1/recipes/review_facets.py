"""ReviewFacets Sys1 Decision Recipe.

Evaluates orthogonal multi-label facets of review feedback against a prompt or plan artifact.
Distinguishes between substantive task revisions (revises_task) and procedure/approach revisions (revises_approach).
"""

from __future__ import annotations

from typing import Any

from pdl_taskmaster.providers.sys1.gating import evaluate_confidence_gate
from pdl_taskmaster.providers.sys1.recipes.base import Sys1Recipe, as_decision_instruction
from pdl_taskmaster.providers.sys1.schema import RecipeResult, Sys1Question, Sys1Request


class ReviewFacetsRecipe(Sys1Recipe):
    """Evaluates multi-label facets of review feedback against a prompt or plan artifact."""

    @property
    def name(self) -> str:
        return "review-facets"

    @property
    def min_confidence(self) -> float:
        return 0.80

    def build_request(self, state: dict[str, Any], **kwargs: Any) -> Sys1Request:
        artifact_kind = state.get("artifact_kind", "prompt")
        content = state.get("content", "")
        feedback = state.get("feedback", "")

        q_task = Sys1Question(
            instructions=as_decision_instruction(
                "Does the user's review feedback modify, add, or remove the core task requirements, "
                "goals, inputs, problem constraints, or requested deliverables? "
                "Instructions to explain the algorithm, detail the response plan, show steps, "
                "or clarify procedural methodology do NOT modify the task."
            ),
            criteria={
                "true": "The feedback modifies the core task goal, inputs, problem constraints, or final deliverable requested.",
                "false": "The feedback does not change the core goal or constraints, or only concerns the procedure, algorithm, or plan.",
            },
            choices=["true", "false"],
        )

        q_approach = Sys1Question(
            instructions=as_decision_instruction(
                "Does the user's review feedback modify, specify, or request changes to the procedure, "
                "algorithm, methodology, analysis steps, justification, or response plan without changing the underlying task goal?"
            ),
            criteria={
                "true": "The feedback modifies or requests details on the algorithm, procedure, methodology, steps, or response plan.",
                "false": "The feedback does not alter or comment on the approach, algorithm, or procedure.",
            },
            choices=["true", "false"],
        )

        q_clarify = Sys1Question(
            instructions=as_decision_instruction(
                "Does the user ask a question or request clarification about the protocol, harness, "
                "or artifact contents without giving a directive to change them?"
            ),
            criteria={
                "true": "The feedback is a question asking for clarification or explanation.",
                "false": "The feedback is not a question asking for clarification.",
            },
            choices=["true", "false"],
        )

        q_ack = Sys1Question(
            instructions=as_decision_instruction(
                "Is the feedback purely conversational politeness, greeting, or chatter without requesting any changes?"
            ),
            criteria={
                "true": "The feedback is purely conversational without requesting changes.",
                "false": "The feedback requests changes, gives instructions, or asks a substantive question.",
            },
            choices=["true", "false"],
        )

        return Sys1Request(
            state={
                "artifact_kind": artifact_kind,
                "content": content,
                "feedback": feedback,
            },
            questions={
                "revises_task": q_task,
                "revises_approach": q_approach,
                "requests_clarification": q_clarify,
                "is_acknowledgment": q_ack,
            },
        )

    def parse_response(
        self, response_body: dict[str, Any], *, duration_ms: float = 0.0
    ) -> RecipeResult:
        answers = response_body.get("answers", {})
        labels: dict[str, bool] = {}
        all_passed = True
        min_conf = 1.0

        for key in ["revises_task", "revises_approach", "requests_clarification", "is_acknowledgment"]:
            ans = answers.get(key, {})
            gating = evaluate_confidence_gate(ans, confidence_floor=self.min_confidence)
            if not gating.passed:
                all_passed = False
            min_conf = min(min_conf, gating.confidence)
            labels[key] = (gating.choice == "true")

        # Determine overall verdict
        if labels.get("revises_task") and labels.get("revises_approach"):
            verdict = "revise_task_and_approach"
        elif labels.get("revises_task"):
            verdict = "revise_task"
        elif labels.get("revises_approach"):
            verdict = "revise_approach"
        elif labels.get("requests_clarification"):
            verdict = "clarify"
        elif labels.get("is_acknowledgment"):
            verdict = "acknowledgment"
        else:
            verdict = "none"

        status = "ready" if all_passed else "review"

        return RecipeResult(
            status=status,
            verdict=verdict,
            confidence=min_conf,
            margin=0.0,
            entropy=0.0,
            passed_gating=all_passed,
            probabilities={},
            duration_ms=duration_ms,
            labels=labels,
            metadata=response_body.get("metadata", {}),
        )

    def map_to_wire(self, result: RecipeResult) -> dict[str, Any]:
        labels = result.labels or {}
        if labels.get("requests_clarification"):
            return {"kind": "PROTOCOL_DISCUSSION"}
        if labels.get("revises_task") or labels.get("revises_approach"):
            task_dims = ["OTHER_TASK_OR_RESULT"] if labels.get("revises_task") else []
            app_dims = ["JUSTIFICATION_PROCEDURE"] if labels.get("revises_approach") else []
            return {
                "kind": "REVIEW_FACTS",
                "task_change_dimensions": task_dims,
                "approach_change_dimensions": app_dims,
                "progression_requested": False,
            }
        if labels.get("is_acknowledgment"):
            return {"kind": "SUBSTANTIVE_DISCUSSION"}
        return {"kind": "UNRESOLVED"}
