from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
import re
import tempfile
import hashlib

from controller.mechanical_controller import (
    AtomicJsonStore,
    ControllerError,
    Intent,
    MechanicalController,
    NextAction,
    ProtocolState,
    ReviewDecision,
    Stage,
    Transition,
)
from runtime.operation_bridge import ActivationRoute, ModelRequest, OperationBridge, WireError
from runtime.quarantine import compile_bootstrap_output
from runtime.workspace import WorkspaceError, WorkspaceRun
from runtime import presentation


ModelCall = Callable[[ModelRequest], str]


_EXPLICIT_INVOCATION = re.compile(
    r"^\s*(?:(?:please\s+)?(?:(?:could|can|would)\s+you\s+)?(?:use|apply|invoke|run)\s+)?"
    r"(?:\$confirm-with-pseudocode|\[\$confirm-with-pseudocode\]\([^)]+\))"
    r"\s*(?:(?:to)\b|[.:,;-])?\s*(?P<body>.*)$",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class InvocationObservation:
    explicit: bool
    substantive_request: str


def observe_invocation(user_message: str) -> InvocationObservation:
    """Recognize host-visible leading skill invocation syntax.

    Only the leading control wrapper is removed. Mentions inside the substantive
    request remain data, including tasks whose subject is this protocol.
    """
    match = _EXPLICIT_INVOCATION.match(user_message)
    if not match:
        return InvocationObservation(False, user_message.strip())
    return InvocationObservation(True, match.group("body").strip())


@dataclass
class CallTrace:
    operation: str
    projection_manifest: dict[str, Any]
    model_text: str
    workspace_stage: str
    workspace_invocation_id: str


@dataclass
class EngineResponse:
    text: str | None
    traces: list[CallTrace] = field(default_factory=list)
    bypass: bool = False
    closed: bool = False


class SessionEngine:
    """Condition C session orchestrator.

    Control flow is owned by MechanicalController. Context flow and durable
    stage-to-stage handoff are owned by WorkspaceRun. Semantic worker calls are
    stateless and receive only the operation projection compiled from the
    materialized stage inputs plus applicable Standard clauses.
    """

    def __init__(
        self,
        repo_root: str | Path,
        model_call: ModelCall,
        *,
        higher_priority_constraints: Any = None,
        available_execution_tools: Any = None,
        workspace_root: str | Path | None = None,
        render_compact: bool = False,
    ):
        self.repo_root = Path(repo_root)
        self.model_call = model_call
        self.higher_priority_constraints = higher_priority_constraints
        self.available_execution_tools = available_execution_tools
        self.bridge = OperationBridge(self.repo_root, render_compact=render_compact)
        self.controller: Optional[MechanicalController] = None
        self.workspace: Optional[WorkspaceRun] = None
        # Protocol v2: semantic-bootstrap containment (structural, non-optional).
        # Raw untrusted content is read by BOOTSTRAP_ANALYSIS only; every compile
        # operation receives the sanitized compiled analysis. Cache is keyed on
        # the raw source so repeated sources bootstrap once per session.
        self._bootstrap_cache: dict[str, str] = {}
        if workspace_root is None:
            self.workspace_root = Path(tempfile.mkdtemp(prefix="pdl-c0-workspaces-"))
        else:
            self.workspace_root = Path(workspace_root)
            self.workspace_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def restore(
        cls,
        repo_root: str | Path,
        model_call: ModelCall,
        workspace_path: str | Path,
        *,
        higher_priority_constraints: Any = None,
        available_execution_tools: Any = None,
        render_compact: bool = False,
    ) -> "SessionEngine":
        workspace_path = Path(workspace_path)
        engine = cls(
            repo_root,
            model_call,
            higher_priority_constraints=higher_priority_constraints,
            available_execution_tools=available_execution_tools,
            workspace_root=workspace_path.parent,
            render_compact=render_compact,
        )
        workspace = WorkspaceRun.open(repo_root, workspace_path)
        if workspace.protocol_instance_id is None or not workspace.controller_state_path.is_file():
            raise WorkspaceError("restorable_protocol_state_missing")
        store = AtomicJsonStore(workspace.controller_state_path)
        state = store.load()
        if state.instance_id != workspace.protocol_instance_id:
            raise WorkspaceError("restore_instance_binding")
        engine.workspace = workspace
        engine.controller = MechanicalController(state, store)
        workspace.append_event("SESSION_RESTORED", {"instance_id": state.instance_id})
        return engine

    def _new_workspace(self) -> WorkspaceRun:
        return WorkspaceRun.create(self.repo_root, self.workspace_root)

    def _bind_new_controller(self, workspace: WorkspaceRun) -> MechanicalController:
        state = ProtocolState.new()
        workspace.bind_protocol(state.instance_id)
        controller = MechanicalController(state, AtomicJsonStore(workspace.controller_state_path))
        workspace.publish_approach_sources([])
        return controller

    def _invoke(self, request: ModelRequest, traces: list[CallTrace]) -> str:
        model_text = self.model_call(request)
        self.workspace.record_model_output(request.workspace_invocation, model_text)
        traces.append(
            CallTrace(
                request.operation,
                request.manifest,
                model_text,
                request.workspace_invocation.stage,
                request.workspace_invocation.invocation_id,
            )
        )
        return model_text

    def _call(
        self,
        operation: str,
        values: dict[str, Any],
        traces: list[CallTrace],
        parser: Callable[[str], Any] | None = None,
    ) -> Any:
        """Invoke one operation. With a parser, retry ONCE on WireError with an
        operator correction so a sampling glitch (invalid JSON, dropped field)
        costs one extra call instead of fatally failing the session."""
        if self.workspace is None:
            raise WorkspaceError("workspace_not_initialized")
        request = self.bridge.request(
            operation,
            values,
            workspace=self.workspace,
            higher_priority_constraints=self.higher_priority_constraints,
        )
        model_text = self._invoke(request, traces)
        if parser is None:
            return model_text
        try:
            return parser(model_text)
        except WireError as first_error:
            correction = (
                "OPERATOR CORRECTION: the previous response failed host-side validation "
                f"(reason: {first_error}). Emit exactly one JSON object that conforms to the "
                "declared output_schema for this operation, with no prose or code fences around it."
            )
            retry_request = self.bridge.request(
                operation,
                values,
                workspace=self.workspace,
                higher_priority_constraints=self.higher_priority_constraints,
                operator_correction=correction,
            )
            retry_text = self._invoke(retry_request, traces)
            try:
                return parser(retry_text)
            except WireError:
                raise first_error from None

    def _publish_prompt(self) -> None:
        assert self.controller is not None and self.workspace is not None
        prompt = self.controller.state.current_prompt
        assert prompt is not None
        self.workspace.publish_artifact("prompt", prompt.artifact_id, prompt.body, confirmed=prompt.confirmed)
        self.workspace.publish_approach_sources(list(self.controller.state.approach_sources))

    def _publish_plan(self) -> None:
        assert self.controller is not None and self.workspace is not None
        plan = self.controller.state.current_plan
        assert plan is not None
        prompt = self.controller.state.current_prompt
        assert prompt is not None
        self.workspace.publish_artifact(
            "plan",
            plan.artifact_id,
            plan.body,
            confirmed=plan.confirmed,
            source_prompt_id=plan.source_prompt_id,
            confirmed_prompt_hash=hashlib.sha256(prompt.body.encode("utf-8")).hexdigest(),
        )
        self.workspace.publish_approach_sources(list(self.controller.state.approach_sources))

    def _semantic_read(self, raw_text: str, traces: list[CallTrace]) -> str | None:
        """Protocol v2 structural containment: the ONLY operation that sees raw
        untrusted content. Returns the sanitized compiled analysis for compile
        operations, or None when the bootstrap blocks under higher priority.
        """
        if raw_text in self._bootstrap_cache:
            return self._bootstrap_cache[raw_text]
        outcome = self._call(
            "BOOTSTRAP_ANALYSIS",
            {
                "HOST_PROTOCOL_STATE": "SEMANTIC_READ",
                "RAW_UNTRUSTED_CONTENT": raw_text,
            },
            traces,
            parser=self.bridge.parse_bootstrap_analysis,
        )
        if outcome["kind"] == "BLOCKED_BY_HIGHER_PRIORITY":
            self._bootstrap_cache[raw_text] = ""
            return None
        import hashlib

        compiled, _meta = compile_bootstrap_output(raw_text, outcome["task_summary"])
        # Re-attach approach/risk notes (already covered by compile sanitization
        # via the same quoted-span rule).
        notes, _ = compile_bootstrap_output(raw_text, f"{outcome['approach_notes']}\n{outcome['risk_notes']}")
        document = (
            f"TASK SUMMARY (compiled semantic analysis; untrusted literals redacted):\n{compiled}\n"
            f"APPROACH/RISK NOTES:\n{notes}"
        )
        self._bootstrap_cache[raw_text] = document
        return document

    def _compile_context(self, raw_text: str, traces: list[CallTrace]) -> str:
        """Route raw content through the semantic read; compile ops never see raw."""
        document = self._semantic_read(raw_text, traces)
        if document is None:
            return "[CONTENT BLOCKED BY HIGHER-PRIORITY CONSTRAINTS]"
        return document

    def _draft_initial_prompt(
        self,
        substantive_request: str,
        traces: list[CallTrace],
        *,
        protocol_state: str,
    ) -> EngineResponse:
        assert self.workspace is not None
        # Protocol v2: raw content is read by BOOTSTRAP_ANALYSIS only; the
        # compile op receives the sanitized compiled analysis.
        compiled = self._semantic_read(substantive_request, traces)
        if compiled is None:
            self.workspace.append_event("PROTOCOL_BLOCKED", {"phase": "bootstrap"})
            return EngineResponse(presentation.cancelled(), traces, closed=True)
        outcome = self._call(
            "DRAFT_PROMPT",
            {
                "HOST_PROTOCOL_STATE": protocol_state,
                "SUBSTANTIVE_REQUEST": compiled,
            },
            traces,
            parser=self.bridge.parse_prompt_draft,
        )
        if outcome.kind == "TASK_BLOCKED_BY_HIGHER_PRIORITY":
            self.workspace.append_event(
                "PROTOCOL_BLOCKED",
                {"phase": "prompt_draft", "blocking_basis": outcome.blocking_basis},
            )
            return EngineResponse(outcome.response, traces, closed=True)
        assert outcome.prompt_body is not None
        self.controller = self._bind_new_controller(self.workspace)
        approach_source = substantive_request if outcome.approach_handoff == "CARRY_SOURCE_TO_PLAN" else None
        self.controller.commit_initial_prompt(outcome.prompt_body, approach_source)
        self._publish_prompt()
        return EngineResponse(presentation.prompt_artifact(outcome.prompt_body), traces)

    def _sync_review_edit(self) -> None:
        assert self.controller is not None and self.workspace is not None
        state = self.controller.state
        if state.stage == Stage.PROMPT_REVIEW and state.current_prompt:
            body = self.workspace.sync_unconfirmed_edit("prompt", state.current_prompt.artifact_id, state.current_prompt.body)
            if body != state.current_prompt.body:
                self.controller.replace_current_unconfirmed_body("prompt", body)
        elif state.stage == Stage.PLAN_REVIEW and state.current_plan:
            self.workspace.validate_confirmed_artifact(
                "prompt", state.current_prompt.artifact_id, state.current_prompt.body  # type: ignore[union-attr]
            )
            body = self.workspace.sync_unconfirmed_edit("plan", state.current_plan.artifact_id, state.current_plan.body)
            if body != state.current_plan.body:
                self.controller.replace_current_unconfirmed_body("plan", body)

    def _activation(self, user_message: str, traces: list[CallTrace]) -> EngineResponse | None:
        self.workspace = self._new_workspace()
        observation = observe_invocation(user_message)
        if observation.explicit:
            self.workspace.append_event(
                "EXPLICIT_INVOCATION_OBSERVED",
                {"substantive_request_present": bool(observation.substantive_request)},
            )
            return self._draft_initial_prompt(
                observation.substantive_request,
                traces,
                protocol_state="ACTIVE_BY_EXPLICIT_INVOCATION",
            )
        decision = self._call(
            "INTERPRET_ACTIVATION", {"RAW_USER_MESSAGE": user_message}, traces,
            parser=self.bridge.parse_activation,
        )
        if decision.route == ActivationRoute.BLOCKED_BY_HIGHER_PRIORITY:
            return EngineResponse(decision.response, traces, closed=True)
        if decision.route == ActivationRoute.BYPASS:
            return EngineResponse(None, traces, bypass=True)
        if decision.route == ActivationRoute.PROTOCOL_DISCUSSION:
            return EngineResponse(self._call(
                "ANSWER_PROTOCOL_DISCUSSION",
                {
                    "RAW_PROTOCOL_QUESTION": user_message,
                    "CURRENT_STAGE_CLASS": None,
                    "BOUND_REVIEW_SUBJECT_KIND": None,
                    "BOUND_REVIEW_SUBJECT_BODY": None,
                },
                traces,
                parser=self.bridge.parse_protocol_discussion,
            ), traces)
        return self._draft_initial_prompt(
            user_message.strip(),
            traces,
            protocol_state="ACTIVE_BY_SEMANTIC_REQUEST",
        )

    def _draft_plan(self, transition: Transition, traces: list[CallTrace]) -> EngineResponse:
        assert self.controller is not None and self.workspace is not None
        prompt = self.controller.state.current_prompt
        assert prompt is not None
        self.workspace.validate_confirmed_artifact("prompt", prompt.artifact_id, prompt.body)
        _, prompt_body = self.workspace.read_artifact("prompt")
        carried_raw = self.workspace.read_approach_sources()
        if carried_raw != self.controller.state.approach_sources:
            raise WorkspaceError("approach_source_handoff")
        carried = [self._compile_context(s, traces) for s in carried_raw]
        body = self._call(
            "DRAFT_PLAN",
            {
                "CONFIRMED_PROMPT_BODY": prompt_body,
                "CARRIED_APPROACH_SOURCES": carried,
            },
            traces,
            parser=self.bridge.parse_plan_body,
        )
        self.controller.commit_plan(body)
        self._publish_plan()
        return EngineResponse(presentation.plan_artifact(body), traces)

    def _revise_prompt(self, transition: Transition, traces: list[CallTrace]) -> EngineResponse:
        assert self.controller is not None and self.workspace is not None
        prompt = self.controller.state.current_prompt
        assert prompt is not None
        meta, prompt_body = self.workspace.read_artifact("prompt")
        if meta.get("artifact_id") != prompt.artifact_id or prompt_body != prompt.body:
            raise WorkspaceError("prompt_revision_handoff")
        change_id = transition.payload["change_id"]
        had_plan = self.controller.state.current_plan is not None
        try:
            body = self._call(
                "REVISE_PROMPT",
                {
                    "CURRENT_PROMPT_BODY": prompt_body,
                    # Protocol v2: raw change source routed through the
                    # semantic read; compile op receives the compiled form.
                    "TASK_CHANGE_SOURCE": self._compile_context(
                        transition.payload["task_change_source"], traces
                    ),
                },
                traces,
                parser=self.bridge.parse_prompt_body,
            )
            self.controller.commit_prompt_revision(change_id, body)
        except Exception:
            self.controller.abort_pending_change(change_id)
            raise
        if had_plan:
            self.workspace.invalidate_artifact("plan", "prompt_revision")
        self._publish_prompt()
        return EngineResponse(presentation.prompt_artifact(body), traces)

    def _revise_plan(self, transition: Transition, traces: list[CallTrace]) -> EngineResponse:
        assert self.controller is not None and self.workspace is not None
        prompt = self.controller.state.current_prompt
        plan = self.controller.state.current_plan
        assert prompt is not None and plan is not None
        self.workspace.validate_confirmed_artifact("prompt", prompt.artifact_id, prompt.body)
        prompt_body = self.workspace.read_artifact("prompt")[1]
        plan_meta, plan_body = self.workspace.read_artifact("plan")
        if plan_meta.get("artifact_id") != plan.artifact_id or plan_body != plan.body:
            raise WorkspaceError("plan_revision_handoff")
        change_id = transition.payload["change_id"]
        carried_raw = self.workspace.read_approach_sources()
        if carried_raw != self.controller.state.approach_sources:
            raise WorkspaceError("approach_source_handoff")
        try:
            body = self._call(
                "REVISE_PLAN",
                {
                    "CONFIRMED_PROMPT_BODY": prompt_body,
                    "CURRENT_PLAN_BODY": plan_body,
                    "CARRIED_APPROACH_SOURCES": [
                        *map(lambda s: self._compile_context(s, traces), carried_raw),
                        self._compile_context(transition.payload["approach_change_source"], traces),
                    ],
                },
                traces,
                parser=self.bridge.parse_plan_body,
            )
            self.controller.commit_plan_revision(change_id, body)
        except Exception:
            self.controller.abort_pending_change(change_id)
            raise
        self._publish_plan()
        return EngineResponse(presentation.plan_artifact(body), traces)

    def _execute(self, transition: Transition, traces: list[CallTrace]) -> EngineResponse:
        assert self.controller is not None and self.workspace is not None
        if not self.controller.can_execute():
            raise ControllerError("execute_gate")
        prompt = self.controller.state.current_prompt
        plan = self.controller.state.current_plan
        assert prompt is not None and plan is not None
        self.workspace.validate_confirmed_artifact("prompt", prompt.artifact_id, prompt.body)
        self.workspace.validate_confirmed_artifact("plan", plan.artifact_id, plan.body)
        prompt_body = self.workspace.read_artifact("prompt")[1]
        plan_body = self.workspace.read_artifact("plan")[1]
        # Protocol v2: the supplied execution input is raw user content (in the
        # adversarial battery it IS the untrusted block). Route it through the
        # semantic read — compile ops never receive raw content in any symbol.
        supplied_raw = transition.payload.get("execution_input_source")
        supplied_compiled = self._compile_context(supplied_raw, traces) if supplied_raw else None
        outcome = self._call(
            "EXECUTE",
            {
                "CONFIRMED_PROMPT_BODY": prompt_body,
                "CONFIRMED_PLAN_BODY": plan_body,
                "REQUIRED_TASK_INPUTS": None,
                "SUPPLIED_EXECUTION_INPUT_SOURCE": supplied_compiled,
                "AVAILABLE_EXECUTION_TOOLS": self.available_execution_tools,
            },
            traces,
            parser=self.bridge.parse_execution,
        )
        if outcome.kind == "REQUEST_INPUT":
            assert outcome.expected_type is not None and outcome.description is not None
            self.controller.request_execution_input(outcome.expected_type, outcome.description)
            self.workspace.publish_execution_outcome(
                outcome.kind,
                outcome.body,
                {"expected_type": outcome.expected_type, "description": outcome.description},
            )
            return EngineResponse(outcome.body, traces)
        if outcome.kind == "BLOCKED_BY_HIGHER_PRIORITY":
            self.controller.cancel()
            self.workspace.publish_execution_outcome(outcome.kind, outcome.body)
            return EngineResponse(outcome.body, traces, closed=True)
        result_body_hash = hashlib.sha256(outcome.body.encode("utf-8")).hexdigest()
        self.controller.complete_success(result_body_hash)
        self.workspace.publish_execution_outcome(
            outcome.kind,
            outcome.body,
            {
                "source_prompt_id": prompt.artifact_id,
                "source_plan_id": plan.artifact_id,
                "result_body_hash": result_body_hash,
                "confirmed_prompt_hash": hashlib.sha256(prompt.body.encode("utf-8")).hexdigest(),
                "confirmed_plan_hash": hashlib.sha256(plan.body.encode("utf-8")).hexdigest(),
            },
        )
        return EngineResponse(outcome.body, traces, closed=True)

    def _answer_protocol(self, user_message: str, traces: list[CallTrace]) -> EngineResponse:
        assert self.controller is not None
        kind, body = self.controller.review_subject()
        return EngineResponse(self._call(
            "ANSWER_PROTOCOL_DISCUSSION",
            {
                "RAW_PROTOCOL_QUESTION": user_message,
                "CURRENT_STAGE_CLASS": self.controller.state.stage.value,
                "BOUND_REVIEW_SUBJECT_KIND": kind,
                "BOUND_REVIEW_SUBJECT_BODY": body,
            },
            traces,
            parser=self.bridge.parse_protocol_discussion,
        ), traces)

    def _apply_transition(self, transition: Transition, user_message: str, traces: list[CallTrace]) -> EngineResponse:
        if transition.action == NextAction.DRAFT_PLAN:
            return self._draft_plan(transition, traces)
        if transition.action == NextAction.REVISE_PROMPT:
            return self._revise_prompt(transition, traces)
        if transition.action == NextAction.REVISE_PLAN:
            return self._revise_plan(transition, traces)
        if transition.action == NextAction.EXECUTE:
            return self._execute(transition, traces)
        if transition.action == NextAction.ANSWER_PROTOCOL:
            return self._answer_protocol(user_message, traces)
        if transition.action == NextAction.DEFER_SUBSTANTIVE:
            return EngineResponse(presentation.deferred_substantive(), traces)
        if transition.action == NextAction.REQUEST_REVIEW_CLARIFICATION:
            return EngineResponse(presentation.review_clarification(), traces)
        if transition.action == NextAction.SHOW_CURRENT_PROMPT:
            assert self.controller is not None and self.workspace is not None
            prompt = self.controller.state.current_prompt
            assert prompt is not None
            self.workspace.publish_approach_sources(list(self.controller.state.approach_sources))
            return EngineResponse(presentation.prompt_artifact(self.workspace.read_artifact("prompt")[1]), traces)
        if transition.action == NextAction.CLOSED:
            assert self.workspace is not None
            self.workspace.append_event("PROTOCOL_CLOSED", {"reason": "cancelled"})
            return EngineResponse(presentation.cancelled(), traces, closed=True)
        if transition.action == NextAction.START_NEW_INSTANCE:
            new_task = transition.payload["new_task_source"]
            assert self.workspace is not None
            self.workspace.append_event("PROTOCOL_CLOSED", {"reason": "new_task"})
            self.workspace = self._new_workspace()
            self.controller = None
            return self._draft_initial_prompt(
                new_task,
                traces,
                protocol_state="ACTIVE_FRESH_INSTANCE_FROM_REVIEW",
            )
        raise ControllerError(f"transition:{transition.action.value}")

    def handle_user_message(self, user_message: str) -> EngineResponse:
        traces: list[CallTrace] = []
        if self.controller is None or self.controller.state.stage in {Stage.CLOSED_SUCCESS, Stage.CLOSED_CANCELLED}:
            return self._activation(user_message, traces) or EngineResponse(None, traces, bypass=True)

        if self.workspace is None:
            raise WorkspaceError("active_controller_without_workspace")
        if self.controller.state.stage not in {Stage.PROMPT_REVIEW, Stage.PLAN_REVIEW, Stage.WAITING_INPUT}:
            raise ControllerError("user_message_stage")

        self._sync_review_edit()
        subject_kind, subject_body = self.controller.review_subject()
        previous_stage = self.controller.state.stage
        operation, parser = {
            Stage.PROMPT_REVIEW: ("INTERPRET_PROMPT_REVIEW", self.bridge.parse_prompt_review),
            Stage.PLAN_REVIEW: ("INTERPRET_PLAN_REVIEW", self.bridge.parse_plan_review),
            Stage.WAITING_INPUT: ("INTERPRET_EXECUTION_INPUT", self.bridge.parse_execution_input),
        }[previous_stage]
        decision = ReviewDecision.from_dict(self._call(
            operation,
            {
                "BOUND_REVIEW_SUBJECT_KIND": subject_kind,
                "BOUND_REVIEW_SUBJECT_BODY": subject_body,
                "RAW_USER_REVIEW_MESSAGE": user_message,
            },
            traces,
            parser=parser,
        ))
        transition = self.controller.apply_review_decision(decision, user_message)

        if decision.intent == Intent.ACCEPT_CURRENT:
            if previous_stage == Stage.PROMPT_REVIEW:
                prompt = self.controller.state.current_prompt
                assert prompt is not None
                self.workspace.mark_artifact_confirmed("prompt", prompt.artifact_id)
            elif previous_stage == Stage.PLAN_REVIEW:
                plan = self.controller.state.current_plan
                assert plan is not None
                self.workspace.mark_artifact_confirmed("plan", plan.artifact_id)
        if decision.intent == Intent.REVISE_APPROACH and previous_stage == Stage.PROMPT_REVIEW:
            self.workspace.publish_approach_sources(list(self.controller.state.approach_sources))

        return self._apply_transition(transition, user_message, traces)
