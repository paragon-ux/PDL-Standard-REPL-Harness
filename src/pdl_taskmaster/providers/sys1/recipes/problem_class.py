"""ProblemClass Sys1 Decision Recipe (P0).

Classifies whether an incoming request requires verified execution (combinatorial
existence, exact witness checking, mathematical verification) or standard execution.
"""

from __future__ import annotations

import re
from typing import Any

from pdl_taskmaster.providers.sys1.gating import evaluate_confidence_gate
from pdl_taskmaster.providers.sys1.recipes.base import Sys1Recipe, as_decision_instruction
from pdl_taskmaster.providers.sys1.schema import RecipeResult, Sys1Question, Sys1Request

# Deterministic regex patterns for combinatorial existence and exact witness problems
_COMBINATORIAL_PATTERNS = re.compile(
    r"(?i)\b(?:schur\s+triples?|partitioned?\b[^.\n]*\btriples?|sum\s+triples?|"
    r"subset\s*sum|exact\s+cover|(?:graph\s+)?(?:\d+-)?coloring|graph\s+color|clique\b|hamiltonian\b|"
    r"boolean\s+satisfiability|\bsat\s+solver|combinatorial\s+(?:existence|structure|optimization)|"
    r"minimal\s+(?:cut|partition)\s+palindrome|palindrome\s+partitioning|"
    r"does\s+(?:there\s+exist|a\s+valid\s+partition\s+exist)|is\s+it\s+possible\s+to\s+partition)\b"
)


class ProblemClassRecipe(Sys1Recipe):
    """Evaluates whether an incoming request requires verified execution."""

    @property
    def name(self) -> str:
        return "problem-class"

    @property
    def min_confidence(self) -> float:
        return 0.85

    def build_request(self, state: dict[str, Any], **kwargs: Any) -> Sys1Request:
        task_text = state.get("request", "") or state.get("task_summary", "")
        instruction = as_decision_instruction(
            "Classify whether this task requires verified execution: does it ask whether a combinatorial "
            "structure exists, ask for an exact/optimal solution with a verifiable witness, or is it "
            "standard execution?"
        )
        criteria = {
            "VERIFIED_EXECUTION": (
                "The task asks whether a combinatorial structure exists (e.g. partition into sum triples, "
                "subset sum, coloring, matching, SAT) or asks for an exact/optimal mathematical or algorithmic "
                "solution with a checkable witness."
            ),
            "STANDARD_EXECUTION": (
                "The task is standard programming, drafting, text manipulation, explanation, analytical reasoning, "
                "symbolic/algebraic deduction, word problems, or does not require deterministic combinatorial witness verification."
            ),
        }
        question = Sys1Question(
            instructions=instruction,
            criteria=criteria,
            choices=["VERIFIED_EXECUTION", "STANDARD_EXECUTION"],
        )
        return Sys1Request(
            state={"request": task_text},
            questions={"problem_class": question},
        )

    def parse_response(
        self, response_body: dict[str, Any], *, duration_ms: float = 0.0
    ) -> RecipeResult:
        answers = response_body.get("answers", {})
        ans = answers.get("problem_class", {})
        gating = evaluate_confidence_gate(ans, confidence_floor=self.min_confidence)
        choice = gating.choice or "STANDARD_EXECUTION"
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
            "requires_verified_execution": result.verdict == "VERIFIED_EXECUTION",
            "confidence": result.confidence,
        }

    @staticmethod
    def classify_text_deterministic(text: str) -> bool:
        """Fast-path deterministic classifier based on problem signatures."""
        return bool(_COMBINATORIAL_PATTERNS.search(text or ""))
