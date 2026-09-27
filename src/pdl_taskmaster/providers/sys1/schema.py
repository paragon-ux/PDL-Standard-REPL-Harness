"""Data schemas for Sys1 requests, questions, and recipe results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RecipeStatus = Literal["ready", "review"]


@dataclass(frozen=True)
class Sys1Question:
    """Definition of a question for Sys1 single-pass classification."""

    instructions: str
    criteria: dict[str, str]
    question_type: str = "choice"
    choices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.question_type,
            "instructions": self.instructions,
            "criteria": self.criteria,
        }
        if self.choices:
            result["choices"] = self.choices
        else:
            result["choices"] = list(self.criteria.keys())
        return result


@dataclass(frozen=True)
class Sys1Request:
    """Wire payload sent to the Sys1 classification backend."""

    state: dict[str, Any]
    questions: dict[str, Sys1Question]
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "state": self.state,
            "questions": {k: q.to_dict() for k, q in self.questions.items()},
        }
        if self.model:
            payload["model"] = self.model
        return payload


@dataclass(frozen=True)
class RecipeResult:
    """Unified outcome of evaluating a Sys1 Recipe."""

    status: RecipeStatus
    verdict: str
    confidence: float
    margin: float
    entropy: float
    passed_gating: bool
    probabilities: dict[str, float] = field(default_factory=dict)
    duration_ms: float = 0.0
    model: str | None = None
    usage: dict[str, int] | None = None
    labels: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
