from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
import re
import tempfile

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
from runtime.operation_bridge import ActivationRoute, ModelRequest, OperationBridge
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
    ):
        self.repo_root = Path(repo_root)
        self.model_call = model_call
        self.higher_priority_constraints = higher_priority_constraints
        self.available_execution_tools = available_execution_tools
        self.bridge = OperationBridge(self.repo_root)
        self.controller: Optional[MechanicalController] = None
        self.workspace: Optional[WorkspaceRun] = None
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
    ) -> "SessionEngine":
        workspace_path = Path(workspace_path)
        engine = cls(
            repo_root,
            model_call,
            higher_priority_constraints=higher_priority_constraints,
            available_execution_tools=available_execution_tools,
            workspace_root=workspace_path.parent,
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

    def _call(self, operation: str, values: dict[str, Any], traces: list[CallTrace]) -> str:
        if self.workspace is None:
            raise WorkspaceError("workspace_not_initialized")
        request = self.bridge.request(
            operation,
            values,
            workspace=self.workspace,
            higher_priority_constraints=self.higher_priority_constraints,
        )
        model_text = self.model_call(request)
        self.workspace.record_model_output(request.workspace_invocation, model_text)
        traces.append(
            CallTrace(
                operation,
                request.manifest,
                model_text,
                request.workspace_invocation.stage,
                request.workspace_invocation.invocation_id,
            )
        )
        return model_text

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
        self.workspace.publish_artifact(
            "plan",
            plan.artifact_id,
            plan.body,
            confirmed=plan.confirmed,
            source_prompt_id=plan.source_prompt_id,
        )
        self.workspace.publish_approach_sources(list(self.controller.state.approach_sources))

    def _draft_initial_prompt(
        self,
        substantive_request: str,
        traces: list[CallTrace],
        *,
        protocol_state: str,
    ) -> EngineResponse:
        assert self.workspace is not None
        raw = self._call(
            "DRAFT_PROMPT",
            {
                "HOST_PROTOCOL_STATE": protocol_state,
                "SUBSTANTIVE_REQUEST": substantive_request,
            },
            traces,
        )
        outcome = self.bridge.parse_prompt_draft(raw)
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
        raw = self._call("INTERPRET_ACTIVATION", {"RAW_USER_MESSAGE": user_message}, traces)
        decision = self.bridge.parse_activation(raw)
        if decision.route == ActivationRoute.BLOCKED_BY_HIGHER_PRIORITY:
            return EngineResponse(decision.response, traces, closed=True)
        if decision.route == ActivationRoute.BYPASS:
            return EngineResponse(None, traces, bypass=True)
        if decision.route == ActivationRoute.PROTOCOL_DISCUSSION:
            raw = self._call(
                "ANSWER_PROTOCOL_DISCUSSION",
                {
                    "RAW_PROTOCOL_QUESTION": user_message,
                    "CURRENT_STAGE_CLASS": None,
                    "BOUND_REVIEW_SUBJECT_KIND": None,
                    "BOUND_REVIEW_SUBJECT_BODY": None,
                },
                traces,
            )
            return EngineResponse(self.bridge.parse_protocol_discussion(raw), traces)
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
        carried = self.workspace.read_approach_sources()
        if carried != self.controller.state.approach_sources:
            raise WorkspaceError("approach_source_handoff")
        raw = self._call(
            "DRAFT_PLAN",
            {
                "CONFIRMED_PROMPT_BODY": prompt_body,
                "CARRIED_APPROACH_SOURCES": carried,
            },
            traces,
        )
        body = self.bridge.parse_plan_body(raw)
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
            raw = self._call(
                "REVISE_PROMPT",
                {
                    "CURRENT_PROMPT_BODY": prompt_body,
                    "TASK_CHANGE_SOURCE": transition.payload["task_change_source"],
                },
                traces,
            )
            body = self.bridge.parse_prompt_body(raw)
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
        carried = self.workspace.read_approach_sources()
        if carried != self.controller.state.approach_sources:
            raise WorkspaceError("approach_source_handoff")
        try:
            raw = self._call(
                "REVISE_PLAN",
                {
                    "CONFIRMED_PROMPT_BODY": prompt_body,
                    "CURRENT_PLAN_BODY": plan_body,
                    "CARRIED_APPROACH_SOURCES": [*carried, transition.payload["approach_change_source"]],
                },
                traces,
            )
            body = self.bridge.parse_plan_body(raw)
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
        raw = self._call(
            "EXECUTE",
            {
                "CONFIRMED_PROMPT_BODY": prompt_body,
                "CONFIRMED_PLAN_BODY": plan_body,
                "REQUIRED_TASK_INPUTS": None,
                "SUPPLIED_EXECUTION_INPUT_SOURCE": transition.payload.get("execution_input_source"),
                "AVAILABLE_EXECUTION_TOOLS": self.available_execution_tools,
            },
            traces,
        )
        outcome = self.bridge.parse_execution(raw)
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
        self.controller.complete_success()
        self.workspace.publish_execution_outcome(outcome.kind, outcome.body)
        return EngineResponse(outcome.body, traces, closed=True)

    def _answer_protocol(self, user_message: str, traces: list[CallTrace]) -> EngineResponse:
        assert self.controller is not None
        kind, body = self.controller.review_subject()
        raw = self._call(
            "ANSWER_PROTOCOL_DISCUSSION",
            {
                "RAW_PROTOCOL_QUESTION": user_message,
                "CURRENT_STAGE_CLASS": self.controller.state.stage.value,
                "BOUND_REVIEW_SUBJECT_KIND": kind,
                "BOUND_REVIEW_SUBJECT_BODY": body,
            },
            traces,
        )
        return EngineResponse(self.bridge.parse_protocol_discussion(raw), traces)

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
        raw = self._call(
            operation,
            {
                "BOUND_REVIEW_SUBJECT_KIND": subject_kind,
                "BOUND_REVIEW_SUBJECT_BODY": subject_body,
                "RAW_USER_REVIEW_MESSAGE": user_message,
            },
            traces,
        )
        decision = ReviewDecision.from_dict(parser(raw))
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
