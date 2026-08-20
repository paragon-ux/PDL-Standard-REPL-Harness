from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import json
import os
import tempfile
import uuid


SCHEMA_VERSION = "C0-HOST-3"


class ControllerError(RuntimeError):
    pass


class Stage(str, Enum):
    PROMPT_REQUIRED = "PROMPT_REQUIRED"
    PROMPT_REVIEW = "PROMPT_REVIEW"
    PLAN_REQUIRED = "PLAN_REQUIRED"
    PLAN_REVIEW = "PLAN_REVIEW"
    EXECUTION_READY = "EXECUTION_READY"
    WAITING_INPUT = "WAITING_INPUT"
    OUTCOME_UNCERTAIN = "OUTCOME_UNCERTAIN"
    CLOSED_SUCCESS = "CLOSED_SUCCESS"
    CLOSED_CANCELLED = "CLOSED_CANCELLED"


class Intent(str, Enum):
    ACCEPT_CURRENT = "ACCEPT_CURRENT"
    REVISE_TASK = "REVISE_TASK"
    REVISE_APPROACH = "REVISE_APPROACH"
    NEW_TASK = "NEW_TASK"
    CANCEL = "CANCEL"
    PROTOCOL_DISCUSSION = "PROTOCOL_DISCUSSION"
    SUBSTANTIVE_DISCUSSION = "SUBSTANTIVE_DISCUSSION"
    SUPPLY_EXECUTION_INPUT = "SUPPLY_EXECUTION_INPUT"
    UNRESOLVED = "UNRESOLVED"


class NextAction(str, Enum):
    NONE = "NONE"
    DRAFT_PROMPT = "DRAFT_PROMPT"
    REVISE_PROMPT = "REVISE_PROMPT"
    DRAFT_PLAN = "DRAFT_PLAN"
    REVISE_PLAN = "REVISE_PLAN"
    EXECUTE = "EXECUTE"
    ANSWER_PROTOCOL = "ANSWER_PROTOCOL"
    DEFER_SUBSTANTIVE = "DEFER_SUBSTANTIVE"
    REQUEST_REVIEW_CLARIFICATION = "REQUEST_REVIEW_CLARIFICATION"
    START_NEW_INSTANCE = "START_NEW_INSTANCE"
    CLOSED = "CLOSED"
    RESOLVE_OUTCOME = "RESOLVE_OUTCOME"
    SHOW_CURRENT_PROMPT = "SHOW_CURRENT_PROMPT"


@dataclass
class Artifact:
    artifact_id: str
    body: str
    confirmed: bool = False
    source_prompt_id: Optional[str] = None


@dataclass
class PendingChange:
    change_id: str
    source_message: str
    changes_task: bool = False
    changes_approach: bool = False


@dataclass
class PendingInput:
    input_id: str
    expected_type: str
    description: str


@dataclass
class InFlightAction:
    action_id: str
    description: str


@dataclass
class ReviewDecision:
    intent: Intent
    also_changes_approach: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReviewDecision":
        return cls(
            intent=Intent(value["intent"]),
            also_changes_approach=value.get("also_changes_approach", False),
        )


@dataclass
class Transition:
    action: NextAction
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProtocolState:
    schema_version: str
    instance_id: str
    stage: Stage
    prompt_highwater: int = 0
    plan_highwater: int = 0
    action_highwater: int = 0
    current_prompt: Optional[Artifact] = None
    current_plan: Optional[Artifact] = None
    pending_change: Optional[PendingChange] = None
    approach_sources: list[str] = field(default_factory=list)
    pending_input: Optional[PendingInput] = None
    in_flight_action: Optional[InFlightAction] = None

    @classmethod
    def new(cls, instance_id: Optional[str] = None) -> "ProtocolState":
        return cls(
            schema_version=SCHEMA_VERSION,
            instance_id=instance_id or f"I-{uuid.uuid4().hex[:10]}",
            stage=Stage.PROMPT_REQUIRED,
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["stage"] = self.stage.value
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProtocolState":
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ControllerError("checkpoint_schema")
        state = cls(
            schema_version=value["schema_version"],
            instance_id=value["instance_id"],
            stage=Stage(value["stage"]),
            prompt_highwater=int(value.get("prompt_highwater", 0)),
            plan_highwater=int(value.get("plan_highwater", 0)),
            action_highwater=int(value.get("action_highwater", 0)),
            current_prompt=Artifact(**value["current_prompt"]) if value.get("current_prompt") else None,
            current_plan=Artifact(**value["current_plan"]) if value.get("current_plan") else None,
            pending_change=PendingChange(**value["pending_change"]) if value.get("pending_change") else None,
            approach_sources=list(value.get("approach_sources", [])),
            pending_input=PendingInput(**value["pending_input"]) if value.get("pending_input") else None,
            in_flight_action=InFlightAction(**value["in_flight_action"]) if value.get("in_flight_action") else None,
        )
        state.validate()
        if state.in_flight_action and state.stage not in {Stage.CLOSED_SUCCESS, Stage.CLOSED_CANCELLED}:
            state.stage = Stage.OUTCOME_UNCERTAIN
        return state

    def validate(self) -> None:
        if min(self.prompt_highwater, self.plan_highwater, self.action_highwater) < 0:
            raise ControllerError("negative_highwater")
        if any(not isinstance(item, str) or not item.strip() for item in self.approach_sources):
            raise ControllerError("approach_source_state")
        if self.pending_change:
            if not self.pending_change.source_message.strip():
                raise ControllerError("pending_change_source")
            if not (self.pending_change.changes_task or self.pending_change.changes_approach):
                raise ControllerError("pending_change_effect")
        if self.current_prompt and not self.current_prompt.artifact_id.startswith(f"{self.instance_id}-P"):
            raise ControllerError("prompt_instance")
        if self.current_plan:
            if not self.current_plan.artifact_id.startswith(f"{self.instance_id}-R"):
                raise ControllerError("plan_instance")
            if not self.current_prompt:
                raise ControllerError("plan_without_prompt")
            if self.current_plan.source_prompt_id != self.current_prompt.artifact_id:
                raise ControllerError("plan_source")
        if self.stage in {Stage.PLAN_REQUIRED, Stage.PLAN_REVIEW, Stage.EXECUTION_READY, Stage.WAITING_INPUT, Stage.OUTCOME_UNCERTAIN}:
            if not self.current_prompt or not self.current_prompt.confirmed:
                raise ControllerError("prompt_gate")
        if self.stage in {Stage.PLAN_REVIEW, Stage.EXECUTION_READY, Stage.WAITING_INPUT, Stage.OUTCOME_UNCERTAIN} and not self.current_plan:
            raise ControllerError("plan_missing")
        if self.stage in {Stage.EXECUTION_READY, Stage.WAITING_INPUT, Stage.OUTCOME_UNCERTAIN}:
            if not self.current_plan or not self.current_plan.confirmed:
                raise ControllerError("plan_gate")
        if self.stage == Stage.WAITING_INPUT and not self.pending_input:
            raise ControllerError("waiting_descriptor")
        if self.stage != Stage.WAITING_INPUT and self.pending_input:
            raise ControllerError("unexpected_pending_input")
        if self.stage in {Stage.CLOSED_SUCCESS, Stage.CLOSED_CANCELLED} and (self.pending_change or self.pending_input):
            raise ControllerError("closed_pending_work")


class AtomicJsonStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, state: ProtocolState) -> None:
        state.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def load(self) -> ProtocolState:
        return ProtocolState.from_dict(json.loads(self.path.read_text(encoding="utf-8")))


class MechanicalController:
    def __init__(self, state: Optional[ProtocolState] = None, store: Optional[AtomicJsonStore] = None):
        self.state = state or ProtocolState.new()
        self.store = store
        self._commit()

    def _commit(self) -> None:
        self.state.validate()
        if self.store:
            self.store.save(self.state)

    def _next_prompt_id(self) -> str:
        self.state.prompt_highwater += 1
        return f"{self.state.instance_id}-P{self.state.prompt_highwater}"

    def _next_plan_id(self) -> str:
        self.state.plan_highwater += 1
        return f"{self.state.instance_id}-R{self.state.plan_highwater}"

    def review_subject(self) -> tuple[str, str]:
        if self.state.stage == Stage.PROMPT_REVIEW and self.state.current_prompt:
            return "PROMPT_PSEUDOCODE", self.state.current_prompt.body
        if self.state.stage == Stage.PLAN_REVIEW and self.state.current_plan:
            return "RESPONSE_PLAN_PSEUDOCODE", self.state.current_plan.body
        if self.state.stage == Stage.WAITING_INPUT and self.state.pending_input:
            return "EXECUTION_INPUT_REQUEST", self.state.pending_input.description
        raise ControllerError("review_subject")

    def commit_initial_prompt(self, body: str, approach_source: Optional[str] = None) -> Artifact:
        if self.state.stage != Stage.PROMPT_REQUIRED:
            raise ControllerError("initial_prompt_stage")
        artifact = Artifact(self._next_prompt_id(), body)
        self.state.current_prompt = artifact
        self.state.current_plan = None
        if approach_source:
            self.state.approach_sources.append(approach_source)
        self.state.stage = Stage.PROMPT_REVIEW
        self._commit()
        return artifact

    def commit_prompt_revision(self, change_id: str, body: str) -> Artifact:
        change = self.state.pending_change
        if not change or change.change_id != change_id or not change.changes_task:
            raise ControllerError("prompt_revision_change")
        artifact = Artifact(self._next_prompt_id(), body)
        self.state.current_prompt = artifact
        self.state.current_plan = None
        self.state.pending_input = None
        if change.changes_approach:
            self.state.approach_sources.append(change.source_message)
        self.state.pending_change = None
        self.state.stage = Stage.PROMPT_REVIEW
        self._commit()
        return artifact

    def commit_plan(self, body: str) -> Artifact:
        if self.state.stage != Stage.PLAN_REQUIRED:
            raise ControllerError("plan_stage")
        prompt = self.state.current_prompt
        if not prompt or not prompt.confirmed:
            raise ControllerError("plan_prompt")
        artifact = Artifact(self._next_plan_id(), body, source_prompt_id=prompt.artifact_id)
        self.state.current_plan = artifact
        self.state.stage = Stage.PLAN_REVIEW
        self._commit()
        return artifact

    def commit_plan_revision(self, change_id: str, body: str) -> Artifact:
        change = self.state.pending_change
        if not change or change.change_id != change_id or change.changes_task or not change.changes_approach:
            raise ControllerError("plan_revision_change")
        prompt = self.state.current_prompt
        if not prompt or not prompt.confirmed:
            raise ControllerError("plan_revision_prompt")
        artifact = Artifact(self._next_plan_id(), body, source_prompt_id=prompt.artifact_id)
        self.state.current_plan = artifact
        self.state.approach_sources.append(change.source_message)
        self.state.pending_change = None
        self.state.stage = Stage.PLAN_REVIEW
        self._commit()
        return artifact

    def abort_pending_change(self, change_id: str) -> None:
        if self.state.pending_change and self.state.pending_change.change_id == change_id:
            self.state.pending_change = None
            self._commit()

    def _validate_decision(self, decision: ReviewDecision, semantic_source: str) -> None:
        allowed = self.allowed_intents()
        if decision.intent not in allowed:
            raise ControllerError("intent_stage")
        if decision.also_changes_approach and decision.intent != Intent.REVISE_TASK:
            raise ControllerError("secondary_approach_effect")
        source_required = decision.intent in {
            Intent.REVISE_TASK,
            Intent.REVISE_APPROACH,
            Intent.NEW_TASK,
            Intent.SUPPLY_EXECUTION_INPUT,
        }
        if source_required and (not isinstance(semantic_source, str) or not semantic_source.strip()):
            raise ControllerError("semantic_source")

    def allowed_intents(self) -> frozenset[Intent]:
        """Expose the existing stage guard for typed hosts.

        This is a read-only projection of the controller's authoritative
        preconditions; it does not add a transition or alter semantics.
        """
        return frozenset({
            Stage.PROMPT_REVIEW: {
                Intent.ACCEPT_CURRENT, Intent.REVISE_TASK, Intent.REVISE_APPROACH, Intent.NEW_TASK, Intent.CANCEL,
                Intent.PROTOCOL_DISCUSSION, Intent.SUBSTANTIVE_DISCUSSION, Intent.UNRESOLVED,
            },
            Stage.PLAN_REVIEW: {
                Intent.ACCEPT_CURRENT, Intent.REVISE_TASK, Intent.REVISE_APPROACH, Intent.NEW_TASK,
                Intent.CANCEL, Intent.PROTOCOL_DISCUSSION, Intent.SUBSTANTIVE_DISCUSSION, Intent.UNRESOLVED,
            },
            Stage.WAITING_INPUT: {
                Intent.SUPPLY_EXECUTION_INPUT, Intent.REVISE_TASK, Intent.NEW_TASK,
                Intent.CANCEL, Intent.UNRESOLVED,
            },
        }.get(self.state.stage, set()))

    def apply_review_decision(self, decision: ReviewDecision, semantic_source: str) -> Transition:
        self._validate_decision(decision, semantic_source)
        if decision.intent == Intent.UNRESOLVED:
            return Transition(NextAction.REQUEST_REVIEW_CLARIFICATION)
        if decision.intent == Intent.CANCEL:
            self.cancel()
            return Transition(NextAction.CLOSED)
        if decision.intent == Intent.NEW_TASK:
            self.cancel()
            return Transition(NextAction.START_NEW_INSTANCE, {"new_task_source": semantic_source.strip()})
        if decision.intent == Intent.PROTOCOL_DISCUSSION:
            return Transition(NextAction.ANSWER_PROTOCOL)
        if decision.intent == Intent.SUBSTANTIVE_DISCUSSION:
            return Transition(NextAction.DEFER_SUBSTANTIVE)
        if decision.intent == Intent.ACCEPT_CURRENT:
            if self.state.stage == Stage.PROMPT_REVIEW:
                assert self.state.current_prompt is not None
                self.state.current_prompt.confirmed = True
                self.state.stage = Stage.PLAN_REQUIRED
                self._commit()
                return Transition(NextAction.DRAFT_PLAN, {"approach_sources": list(self.state.approach_sources)})
            if self.state.stage == Stage.PLAN_REVIEW:
                assert self.state.current_plan is not None
                self.state.current_plan.confirmed = True
                self.state.stage = Stage.EXECUTION_READY
                self._commit()
                return Transition(NextAction.EXECUTE)
        if decision.intent == Intent.REVISE_TASK:
            change = PendingChange(
                change_id=f"C-{uuid.uuid4().hex[:10]}",
                source_message=semantic_source.strip(),
                changes_task=True,
                changes_approach=decision.also_changes_approach,
            )
            self.state.pending_change = change
            self._commit()
            return Transition(
                NextAction.REVISE_PROMPT,
                {
                    "change_id": change.change_id,
                    "task_change_source": change.source_message,
                },
            )
        if decision.intent == Intent.REVISE_APPROACH:
            source = semantic_source.strip()
            if self.state.stage == Stage.PROMPT_REVIEW:
                self.state.approach_sources.append(source)
                self._commit()
                return Transition(NextAction.SHOW_CURRENT_PROMPT)
            change = PendingChange(
                change_id=f"C-{uuid.uuid4().hex[:10]}",
                source_message=source,
                changes_approach=True,
            )
            self.state.pending_change = change
            self._commit()
            return Transition(
                NextAction.REVISE_PLAN,
                {"change_id": change.change_id, "approach_change_source": change.source_message},
            )
        if decision.intent == Intent.SUPPLY_EXECUTION_INPUT:
            self.state.pending_input = None
            self.state.stage = Stage.EXECUTION_READY
            self._commit()
            return Transition(NextAction.EXECUTE, {"execution_input_source": semantic_source.strip()})
        raise ControllerError("unhandled_decision")

    def replace_current_unconfirmed_body(self, kind: str, body: str) -> None:
        if not isinstance(body, str) or not body.strip():
            raise ControllerError("workspace_artifact_body")
        if kind == "prompt":
            if self.state.stage != Stage.PROMPT_REVIEW or not self.state.current_prompt or self.state.current_prompt.confirmed:
                raise ControllerError("workspace_prompt_edit_stage")
            self.state.current_prompt.body = body.strip()
            self._commit()
            return
        if kind == "plan":
            if self.state.stage != Stage.PLAN_REVIEW or not self.state.current_plan or self.state.current_plan.confirmed:
                raise ControllerError("workspace_plan_edit_stage")
            self.state.current_plan.body = body.strip()
            self._commit()
            return
        raise ControllerError("workspace_artifact_kind")

    def can_execute(self) -> bool:
        state = self.state
        return bool(
            state.stage == Stage.EXECUTION_READY
            and state.current_prompt and state.current_prompt.confirmed
            and state.current_plan and state.current_plan.confirmed
            and state.current_plan.source_prompt_id == state.current_prompt.artifact_id
            and state.pending_input is None
            and state.in_flight_action is None
        )

    def request_execution_input(self, expected_type: str, description: str) -> PendingInput:
        if not self.can_execute():
            raise ControllerError("input_stage")
        pending = PendingInput(f"X-{uuid.uuid4().hex[:10]}", expected_type, description)
        self.state.pending_input = pending
        self.state.stage = Stage.WAITING_INPUT
        self._commit()
        return pending

    def begin_external_action(self, description: str) -> InFlightAction:
        if not self.can_execute():
            raise ControllerError("action_stage")
        self.state.action_highwater += 1
        action = InFlightAction(f"{self.state.instance_id}-A{self.state.action_highwater}", description)
        self.state.in_flight_action = action
        self._commit()
        return action

    def record_external_action_result(self, action_id: str) -> None:
        action = self.state.in_flight_action
        if not action or action.action_id != action_id:
            raise ControllerError("action_result")
        self.state.in_flight_action = None
        self._commit()

    def resolve_uncertain_outcome(self, action_id: str, action_committed: bool) -> Transition:
        if self.state.stage != Stage.OUTCOME_UNCERTAIN:
            raise ControllerError("outcome_stage")
        action = self.state.in_flight_action
        if not action or action.action_id != action_id:
            raise ControllerError("outcome_action")
        self.state.in_flight_action = None
        self.state.stage = Stage.EXECUTION_READY
        self._commit()
        return Transition(NextAction.EXECUTE, {"previous_action_committed": action_committed, "action_id": action_id})

    def complete_success(self) -> None:
        if not self.can_execute():
            raise ControllerError("success_stage")
        self.state.stage = Stage.CLOSED_SUCCESS
        self.state.pending_change = None
        self.state.approach_sources = []
        self._commit()

    def cancel(self) -> None:
        if self.state.stage in {Stage.CLOSED_SUCCESS, Stage.CLOSED_CANCELLED}:
            return
        self.state.pending_change = None
        self.state.approach_sources = []
        self.state.pending_input = None
        self.state.stage = Stage.CLOSED_CANCELLED
        self._commit()

    def new_instance(self, instance_id: Optional[str] = None) -> "MechanicalController":
        if self.state.stage not in {Stage.CLOSED_SUCCESS, Stage.CLOSED_CANCELLED}:
            raise ControllerError("new_instance_stage")
        return MechanicalController(ProtocolState.new(instance_id), self.store)
