from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
import json
import re

from runtime.context_compiler import CompiledProjection, ContextCompiler
from runtime.workspace import WorkspaceInvocation, WorkspaceRun


class WireError(RuntimeError):
    pass


class ActivationRoute(str, Enum):
    APPLY_PROTOCOL = "APPLY_PROTOCOL"
    PROTOCOL_DISCUSSION = "PROTOCOL_DISCUSSION"
    BYPASS = "BYPASS"
    BLOCKED_BY_HIGHER_PRIORITY = "BLOCKED_BY_HIGHER_PRIORITY"


@dataclass(frozen=True)
class ActivationDecision:
    route: ActivationRoute
    response: str | None = None


@dataclass(frozen=True)
class PromptDraftOutcome:
    kind: str
    prompt_body: str | None = None
    approach_handoff: str = "NONE"
    blocking_basis: str | None = None
    response: str | None = None


@dataclass(frozen=True)
class ExecutionOutcome:
    kind: str
    body: str
    expected_type: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ModelRequest:
    projection: CompiledProjection
    prompt: str
    workspace_invocation: WorkspaceInvocation

    @property
    def operation(self) -> str:
        return self.projection.operation

    @property
    def manifest(self) -> dict[str, Any]:
        return self.projection.manifest


class OperationBridge:
    def __init__(self, repo_root: str | Path, *, render_compact: bool = False):
        self.repo_root = Path(repo_root)
        self.render_compact = render_compact
        self.compiler = ContextCompiler(self.repo_root)
        self.bootstrap = (self.repo_root / "runtime" / "worker-bootstrap.txt").read_text(encoding="utf-8")

    def request(
        self,
        operation: str,
        values: dict[str, Any],
        *,
        workspace: WorkspaceRun,
        higher_priority_constraints: Any = None,
        operator_correction: str | None = None,
    ) -> ModelRequest:
        invocation = workspace.materialize_operation(
            operation, values, higher_priority_constraints=higher_priority_constraints
        )
        materialized_values, materialized_higher_priority = workspace.load_operation_values(invocation)
        projection = self.compiler.compile(
            operation,
            materialized_values,
            higher_priority_constraints=materialized_higher_priority,
        )
        workspace.record_projection(invocation, projection.manifest, projection.document)
        prompt = projection.render(self.bootstrap, compact=self.render_compact)
        if operator_correction:
            # Appended outside the projection document so projection_sha256
            # (and fixture replay) stay stable; only used on the retry path.
            prompt = prompt + operator_correction.strip() + "\n"
        return ModelRequest(projection, prompt, invocation)

    @staticmethod
    def _object(model_text: str) -> dict[str, Any]:
        """Extract exactly one JSON object from a worker response.

        Tolerant of *placement* (leading/trailing prose, BOM, markdown fences
        anywhere in the text) but never repairs *content*: malformed JSON
        still raises WireError("invalid_json") so the caller's retry path
        can ask the stateless worker to re-emit (see SessionEngine._call).
        """
        stripped = model_text.strip().lstrip("\ufeff")
        last_error: json.JSONDecodeError | None = None
        value: Any = None
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as exc:
            last_error = exc
        if value is None:
            unfenced = re.sub(r"```(?:json)?", "", stripped).strip()
            try:
                value = json.loads(unfenced)
            except json.JSONDecodeError as exc:
                last_error = exc
        if value is None:
            # Balanced-brace scan: locate the first parseable JSON object
            # embedded in surrounding prose. raw_decode consumes exactly one
            # balanced value starting at each candidate brace.
            decoder = json.JSONDecoder()
            for idx, char in enumerate(stripped):
                if char != "{":
                    continue
                try:
                    candidate, _ = decoder.raw_decode(stripped[idx:])
                except json.JSONDecodeError as exc:
                    last_error = exc
                    continue
                if isinstance(candidate, dict):
                    value = candidate
                    break
        if value is None:
            # Carry the underlying JSONDecodeError detail (e.g. "Invalid
            # \\escape") so the retry's operator correction names the actual
            # defect instead of a generic invalid_json.
            detail = f"invalid_json ({last_error.msg} at column {last_error.pos + 1})" if last_error else "invalid_json"
            raise WireError(detail)
        if not isinstance(value, dict):
            raise WireError("not_object")
        return value

    @staticmethod
    def _keys(value: dict[str, Any], allowed: set[str], required: set[str]) -> None:
        if set(value) - allowed:
            raise WireError("extra_fields")
        if not required <= set(value):
            raise WireError("missing_fields")

    def parse_activation(self, model_text: str) -> ActivationDecision:
        value = self._object(model_text)
        try:
            route = ActivationRoute(value["route"])
        except (KeyError, ValueError, TypeError) as exc:
            raise WireError("activation_route") from exc
        if route == ActivationRoute.BLOCKED_BY_HIGHER_PRIORITY:
            self._keys(value, {"route", "response"}, {"route", "response"})
            response = value["response"]
            if not isinstance(response, str) or not response.strip():
                raise WireError("blocked_response")
            return ActivationDecision(route, response.strip())
        self._keys(value, {"route"}, {"route"})
        return ActivationDecision(route)

    def parse_prompt_draft(self, model_text: str) -> PromptDraftOutcome:
        value = self._object(model_text)
        kind = value.get("kind")
        if kind == "PROMPT":
            self._keys(
                value,
                {"kind", "prompt_body", "approach_handoff"},
                {"kind", "prompt_body", "approach_handoff"},
            )
            body = value["prompt_body"]
            handoff = value["approach_handoff"]
            if not isinstance(body, str) or not body.strip():
                raise WireError("prompt_body")
            if handoff not in {"NONE", "CARRY_SOURCE_TO_PLAN"}:
                raise WireError("approach_handoff")
            return PromptDraftOutcome(kind, body.strip(), handoff)
        if kind == "TASK_BLOCKED_BY_HIGHER_PRIORITY":
            self._keys(
                value,
                {"kind", "blocking_basis", "response"},
                {"kind", "blocking_basis", "response"},
            )
            blocking_basis = value["blocking_basis"]
            if blocking_basis != "PROVIDER_PLATFORM_SAFETY_PRIVACY_PERMISSION_OR_TOOL":
                raise WireError("blocking_basis")
            response = value["response"]
            if not isinstance(response, str) or not response.strip():
                raise WireError("blocked_response")
            return PromptDraftOutcome(kind, blocking_basis=blocking_basis, response=response.strip())
        raise WireError("prompt_draft_kind")

    def _parse_named_body(self, model_text: str, field: str) -> str:
        value = self._object(model_text)
        self._keys(value, {field}, {field})
        body = value[field]
        if not isinstance(body, str) or not body.strip():
            raise WireError(field)
        return body.strip()

    def parse_prompt_body(self, model_text: str) -> str:
        return self._parse_named_body(model_text, "prompt_body")

    def parse_plan_body(self, model_text: str) -> str:
        return self._parse_named_body(model_text, "neutral_plan_body")

    def _parse_artifact_review(self, model_text: str) -> dict[str, Any]:
        value = self._object(model_text)
        kind = value.get("kind")
        if kind == "REVIEW_FACTS":
            self._keys(
                value,
                {"kind", "task_change_dimensions", "approach_change_dimensions", "progression_requested"},
                {"kind", "task_change_dimensions", "approach_change_dimensions", "progression_requested"},
            )
            task_dimensions = value["task_change_dimensions"]
            approach_dimensions = value["approach_change_dimensions"]
            task_allowed = {
                "ACTION_SUBJECT_OR_OBJECT",
                "SCOPE_CONSTRAINT_EXCLUSION_OR_PRIORITY",
                "TIME_FRESHNESS_QUANTITY_OR_CONDITION",
                "COMPARISON_CRITERION_DEFINITION_OR_RELATIONSHIP",
                "AUDIENCE_OR_OUTPUT_CHARACTERISTIC",
                "REQUIRED_CONCLUSION",
                "OTHER_TASK_OR_RESULT",
            }
            approach_allowed = {
                "RESEARCH_OR_EVIDENCE_SELECTION_METHOD",
                "COMPARISON_RANKING_OR_SCORING_METHOD",
                "ANALYSIS_ORDER",
                "JUSTIFICATION_PROCEDURE",
                "OTHER_RESPONSE_PROCEDURE",
            }
            if (
                not isinstance(task_dimensions, list)
                or any(not isinstance(item, str) or item not in task_allowed for item in task_dimensions)
                or len(task_dimensions) != len(set(task_dimensions))
            ):
                raise WireError("task_change_dimensions")
            if (
                not isinstance(approach_dimensions, list)
                or any(not isinstance(item, str) or item not in approach_allowed for item in approach_dimensions)
                or len(approach_dimensions) != len(set(approach_dimensions))
            ):
                raise WireError("approach_change_dimensions")
            progression = value["progression_requested"]
            if not isinstance(progression, bool):
                raise WireError("progression_requested")
            task_changed = bool(task_dimensions)
            approach_changed = bool(approach_dimensions)
            if not (task_changed or approach_changed or progression):
                # All-empty REVIEW_FACTS: the model reports the message changed
                # no dimension and requested no progression. Raising a fatal
                # WireError here disqualified honest models on informational
                # drip turns ("Here is block 1 for inspection..."). Per
                # REVIEW-09 (intent is understood, not uncertain -> not
                # UNRESOLVED), REVIEW-13 (substantive side content is
                # deferred), and REVIEW-14 (silence MUST NOT confirm -> not
                # ACCEPT_CURRENT), the host mechanically treats this as
                # SUBSTANTIVE_DISCUSSION: nothing changes, nothing is
                # confirmed, the session holds its current stage.
                return {"intent": "SUBSTANTIVE_DISCUSSION"}
            if task_changed:
                return {"intent": "REVISE_TASK", "also_changes_approach": approach_changed}
            if approach_changed:
                return {"intent": "REVISE_APPROACH"}
            return {"intent": "ACCEPT_CURRENT"}

        special = {
            "NEW_TASK",
            "CANCEL",
            "PROTOCOL_DISCUSSION",
            "SUBSTANTIVE_DISCUSSION",
            "UNRESOLVED",
        }
        if kind not in special:
            raise WireError("artifact_review_kind")
        self._keys(value, {"kind"}, {"kind"})
        return {"intent": kind}

    def parse_prompt_review(self, model_text: str) -> dict[str, Any]:
        return self._parse_artifact_review(model_text)

    def parse_plan_review(self, model_text: str) -> dict[str, Any]:
        return self._parse_artifact_review(model_text)

    def parse_bootstrap_analysis(self, model_text: str) -> dict[str, Any]:
        value = self._object(model_text)
        kind = value.get("kind")
        if kind == "ANALYSIS":
            self._keys(
                value,
                {"kind", "task_summary", "approach_notes", "risk_notes"},
                {"kind", "task_summary", "approach_notes", "risk_notes"},
            )
            for field in ("task_summary", "approach_notes", "risk_notes"):
                if not isinstance(value[field], str):
                    raise WireError(f"bootstrap_{field}")
            if not value["task_summary"].strip():
                raise WireError("bootstrap_task_summary")
            return {k: value[k] for k in ("kind", "task_summary", "approach_notes", "risk_notes")}
        if kind == "BLOCKED_BY_HIGHER_PRIORITY":
            self._keys(value, {"kind", "response"}, {"kind", "response"})
            response = value["response"]
            if not isinstance(response, str) or not response.strip():
                raise WireError("blocked_response")
            return {"kind": kind, "response": response.strip()}
        raise WireError("bootstrap_kind")

    def parse_execution_input(self, model_text: str) -> dict[str, Any]:
        value = self._object(model_text)
        kind = value.get("kind")
        if kind == "REVISE_TASK":
            self._keys(
                value,
                {"kind", "also_changes_approach"},
                {"kind", "also_changes_approach"},
            )
            if not isinstance(value["also_changes_approach"], bool):
                raise WireError("execution_input_also_changes_approach")
            return {
                "intent": "REVISE_TASK",
                "also_changes_approach": value["also_changes_approach"],
            }
        if kind not in {"SUPPLY_EXECUTION_INPUT", "NEW_TASK", "CANCEL", "UNRESOLVED"}:
            raise WireError("execution_input_kind")
        self._keys(value, {"kind"}, {"kind"})
        return {"intent": kind}

    def parse_protocol_discussion(self, model_text: str) -> str:
        value = self._object(model_text)
        self._keys(value, {"body"}, {"body"})
        body = value["body"]
        if not isinstance(body, str) or not body.strip():
            raise WireError("protocol_body")
        return body.strip()

    def parse_execution(self, model_text: str) -> ExecutionOutcome:
        value = self._object(model_text)
        kind = value.get("kind")
        if kind == "REQUEST_INPUT":
            self._keys(
                value,
                {"kind", "body", "expected_type", "description"},
                {"kind", "body", "expected_type", "description"},
            )
        elif kind in {"RESULT", "BLOCKED_BY_HIGHER_PRIORITY"}:
            self._keys(value, {"kind", "body"}, {"kind", "body"})
        else:
            raise WireError("execution_kind")
        body = value["body"]
        if not isinstance(body, str) or not body.strip():
            raise WireError("execution_body")
        expected_type = value.get("expected_type")
        description = value.get("description")
        if expected_type is not None and (not isinstance(expected_type, str) or not expected_type.strip()):
            raise WireError("execution_expected_type")
        if description is not None and (not isinstance(description, str) or not description.strip()):
            raise WireError("execution_description")
        return ExecutionOutcome(
            kind,
            body.strip(),
            expected_type.strip() if expected_type else None,
            description.strip() if description else None,
        )
