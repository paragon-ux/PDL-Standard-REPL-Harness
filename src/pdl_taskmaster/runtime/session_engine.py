from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
import json
import os
import re
import tempfile
import hashlib

from pdl_taskmaster.controller.mechanical_controller import (
    AtomicJsonStore,
    ControllerError,
    Intent,
    MechanicalController,
    MemoryAtomicJsonStore,
    NextAction,
    ProtocolState,
    ReviewDecision,
    Stage,
    Transition,
)
from pdl_taskmaster.runtime.operation_bridge import ActivationRoute, ModelRequest, OperationBridge, WireError
from pdl_taskmaster.runtime.quarantine import compile_bootstrap_output


def _norm(text: str) -> str:
    """Whitespace-normalized form for verbatim entity matching: collapses all
    whitespace runs to single spaces so formatting variance does not cause
    false entity-miss retries (the 4B check is about content, not layout)."""
    return " ".join((text or "").split())


def _extract_data_payload(raw_text: str) -> str | None:
    """Extract candidate literal execution data blocks from raw user input.

    Recognizes explicit input/data labels (e.g. Input:, Data:, Dataset:,
    Payload:, Target:, Sample:, String:, etc.) or labeled structured blocks.
    Returns the raw extracted payload string, or None if no data block is found.
    """
    if not raw_text or not raw_text.strip():
        return None

    # Search for an explicit input/data section delimiter
    m = re.search(
        r"(?im)^\s*(?:input|inputs|data|dataset|payload|sample\s*input|test\s*cases?|target|query|string|text|array|nums|matrix|sequence)\s*[:=]",
        raw_text,
    )
    if not m:
        return None

    candidate = raw_text[m.start():].strip()
    # If there is a trailing note or instruction separated by double newlines, trim it
    parts = re.split(r"\n\s*\n(?=(?:note|please|make sure|confirm|do not)\b)", candidate, flags=re.IGNORECASE)
    if parts:
        candidate = parts[0].strip()

    return candidate if candidate else None
from pdl_taskmaster.runtime.workspace import MemoryWorkspaceRun, WorkspaceError, WorkspaceRun
from pdl_taskmaster.runtime import presentation


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
        self._bootstrap_cache: dict[tuple[str, str | None], str] = {}
        self._task_entities_cache: dict[tuple[str, str | None], tuple[str, ...]] = {}
        # S4: confirmed deliverable carried from the prior turn (chaining);
        # None for first turns and legacy single-turn workspaces.
        self._previous_deliverable: str | None = None
        self._active_task_entities: tuple[str, ...] = ()
        self._bound_payload_inputs: str | None = None
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
        workspace = MemoryWorkspaceRun.open(repo_root, workspace_path)
        # Pointer may sit on a turn whose controller never committed (e.g. a
        # turn opened by S4 chaining and then interrupted before any model
        # call). Fall back to the most recent turn with a committed,
        # instance-matching state before declaring the session unrestorable.
        candidates: list[tuple[str | None, Path, str | None]] = []
        if workspace.turn_id is not None:
            ordered_ids = [workspace.turn_id]
            turns_dir = workspace.path / "turns"
            if turns_dir.is_dir():
                ordered_ids.extend(
                    d.name for d in sorted(turns_dir.iterdir(), reverse=True)
                    if d.is_dir() and re.match(r"^turn_\d+$", d.name) and d.name != workspace.turn_id
                )
            for turn_id in ordered_ids:
                turn_meta = workspace.read_turn_status(turn_id)
                candidates.append((
                    turn_id,
                    workspace.path / "turns" / turn_id / "state" / "controller-state.json",
                    turn_meta.get("protocol_instance_id") or workspace.protocol_instance_id,
                ))
        else:
            if workspace.protocol_instance_id is None:
                raise WorkspaceError("restorable_protocol_state_missing")
            candidates.append((None, workspace.controller_state_path, workspace.protocol_instance_id))
        restore_state_path: Path | None = None
        for turn_id, candidate_path, expected_instance in candidates:
            if not candidate_path.is_file():
                continue
            candidate_state = json.loads(candidate_path.read_text(encoding="utf-8"))
            if candidate_state.get("instance_id") == expected_instance:
                restore_state_path = candidate_path
                if turn_id is not None and turn_id != workspace.turn_id:
                    workspace.metadata["turn_id"] = turn_id
                    workspace._atomic_write(
                        workspace.metadata_path,
                        json.dumps(workspace.metadata, ensure_ascii=False, indent=2) + "\n",
                    )
                    workspace.turn_id = turn_id
                break
        if restore_state_path is None:
            raise WorkspaceError("restorable_protocol_state_missing")
        store = (
            MemoryAtomicJsonStore(restore_state_path)
            if isinstance(workspace, MemoryWorkspaceRun)
            else AtomicJsonStore(restore_state_path)
        )
        state = store.load()
        if state.instance_id != workspace.protocol_instance_id and workspace.turn_id is None:
            raise WorkspaceError("restore_instance_binding")
        engine.workspace = workspace
        engine.controller = MechanicalController(state, store)
        # Cross-epoch deliverable chaining: repopulate the prior confirmed
        # deliverable on restore. The S4 turn-chaining path sets this field
        # only when a new user message opens a turn in the same process; a
        # resumed epoch (e.g. /confirm in a later REPL invocation) must
        # re-chain it so the execution phase still receives the byte-exact
        # prior deliverable in REQUIRED_TASK_INPUTS. The active turn's status
        # is ACTIVE at restore time, so previous_deliverable() correctly
        # returns the last CLOSED_SUCCESS turn before it.
        engine._previous_deliverable = workspace.previous_deliverable()
        workspace.append_event("SESSION_RESTORED", {"instance_id": state.instance_id})
        return engine

    def _new_workspace(self) -> WorkspaceRun:
        # ADR-0011 / ADR-0008: software-defined in-memory VFS workspace run.
        # Fast, unjournaled writes bypass Windows NTFS fsync latency.
        # Legacy flat workspaces remain supported for direct WorkspaceRun.create callers.
        return MemoryWorkspaceRun.create(self.repo_root, self.workspace_root, turn_id="turn_001")

    def _bind_new_controller(self, workspace: WorkspaceRun) -> MechanicalController:
        state = ProtocolState.new()
        workspace.bind_protocol(state.instance_id)
        store = (
            MemoryAtomicJsonStore(workspace.controller_state_path)
            if isinstance(workspace, MemoryWorkspaceRun)
            else AtomicJsonStore(workspace.controller_state_path)
        )
        controller = MechanicalController(state, store)
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
            feedback = getattr(first_error, "operator_feedback", None)
            if feedback:
                correction = (
                    f"OPERATOR CORRECTION: {feedback}. "
                    "Emit exactly one conforming JSON object matching the declared schema."
                )
            else:
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
        cache_key = (raw_text, self._previous_deliverable)
        if cache_key in self._bootstrap_cache:
            return self._bootstrap_cache[cache_key]
        bootstrap_values: dict[str, Any] = {
            "HOST_PROTOCOL_STATE": "SEMANTIC_READ",
            "RAW_UNTRUSTED_CONTENT": raw_text,
        }
        if self._previous_deliverable:
            # S4: the prior turn's confirmed deliverable is host-published,
            # gate-passed content (never raw untrusted input). It is compiled
            # as inactive background context for the new turn.
            bootstrap_values["PREVIOUS_DELIVERABLE"] = self._previous_deliverable
        outcome = self._call(
            "BOOTSTRAP_ANALYSIS",
            bootstrap_values,
            traces,
            parser=self.bridge.parse_bootstrap_analysis,
        )
        if outcome["kind"] == "BLOCKED_BY_HIGHER_PRIORITY":
            self._bootstrap_cache[cache_key] = ""
            return None
        import hashlib

        compiled, _meta = compile_bootstrap_output(raw_text, outcome["task_summary"])
        # Containment-boundary durability: a lazy semantic read that classifies
        # substantive raw content as instruction-free loses the entire task
        # upstream of every gate. Detect and retry once before compiling.
        summary_lowers = (outcome["task_summary"] or "").lower()
        if len(raw_text) > 500 and (
            "no operative instructions" in summary_lowers
            or "no substantive" in summary_lowers
            or "no requested" in summary_lowers
            or len((outcome["task_summary"] or "").strip()) < 40
        ):
            self.workspace.append_event(
                "BOOTSTRAP_DEGENERATE_READ_RETRY",
                {"raw_chars": len(raw_text), "summary_chars": len(outcome["task_summary"] or "")},
            ) if self.workspace is not None else None
            outcome = self._call(
                "BOOTSTRAP_ANALYSIS",
                bootstrap_values,
                traces,
                parser=self.bridge.parse_bootstrap_analysis,
            )
            if outcome["kind"] == "BLOCKED_BY_HIGHER_PRIORITY":
                self._bootstrap_cache[cache_key] = ""
                return None
            compiled, _meta = compile_bootstrap_output(raw_text, outcome["task_summary"])


        # Mechanical entity containment: a task entity is forwarded downstream
        # ONLY if it is a verbatim substring of the SANITIZED task summary.
        # Hostile tokens (canaries, exploit directives) are replaced by the
        # sanitizer, so a hostile entity can never pass this filter -- the
        # verbatim-preservation channel inherits the compile tier's redaction.
        raw_entities = outcome.get("task_entities") or []
        entities = tuple(
            e for e in raw_entities
            if isinstance(e, str) and e.strip() and e in compiled
        )
        dropped = [e for e in raw_entities if e not in entities]
        if dropped and self.workspace is not None:
            self.workspace.append_event("TASK_ENTITY_DROPPED_UNSAFE", {"count": len(dropped)})
        self._task_entities_cache[cache_key] = entities
        # In Protocol v2 out-of-band field isolation: approach_notes carries TASK-02
        # procedural guidance for planning. risk_notes is quarantined threat data
        # retained in telemetry/traces, not leaked into compile contexts.
        approach = outcome.get("approach_notes", "")
        notes, _ = compile_bootstrap_output(raw_text, approach) if approach else ("", {})
        if "risk_notes" in outcome and isinstance(outcome["risk_notes"], str):
            sanitized_risk, _ = compile_bootstrap_output(raw_text, outcome["risk_notes"])
            outcome["risk_notes"] = sanitized_risk
        document = (
            f"TASK SUMMARY (compiled semantic analysis; untrusted literals redacted):\n{compiled}\n"
            f"APPROACH/RISK NOTES:\n{notes}"
        )
        if entities:
            document += (
                "\nOPERATIVE TASK ENTITIES (copy each EXACTLY, character-for-character, into the "
                "task_entities array AND reproduce each verbatim inside the prompt body):\n"
                + "\n".join(f"- {e}" for e in entities)
            )
        self._bootstrap_cache[cache_key] = document
        return document

    def _compile_context(self, raw_text: str, traces: list[CallTrace]) -> str:
        """Route raw content through the semantic read; compile ops never see raw."""
        document = self._semantic_read(raw_text, traces)
        if document is None:
            return "[CONTENT BLOCKED BY HIGHER-PRIORITY CONSTRAINTS]"
        return document

    def _compile_approach_context(self, raw_text: str, traces: list[CallTrace]) -> str:
        """Route approach content through semantic compilation explicitly labeled as TASK-02."""
        raw_compiled = self._compile_context(raw_text, traces)
        if raw_compiled.startswith("[CONTENT BLOCKED"):
            return raw_compiled
        prefix = "TASK SUMMARY (compiled semantic analysis; untrusted literals redacted):"
        if prefix in raw_compiled:
            parts = raw_compiled.split("APPROACH/RISK NOTES:")
            task_part = parts[0].replace(prefix, "").strip()
            approach_part = parts[1].strip() if len(parts) > 1 else ""
            combined = "\n".join(filter(None, [task_part, approach_part]))
            return f"APPROACH CONSTRAINT (TASK-02 operative requirement; incorporate per PLAN-08):\n{combined}"
        return f"APPROACH CONSTRAINT (TASK-02 operative requirement; incorporate per PLAN-08):\n{raw_compiled.strip()}"


    def _entity_coverage_missing(self, prompt_body: str, entities: tuple[str, ...]) -> list[str]:
        """Mechanical source-coverage check: every forwarded task entity must
        appear verbatim in the prompt IR. Host-side string presence only -- no
        model judgment, no generation constraint."""
        return [e for e in entities if e not in prompt_body]

    def _enforce_entity_coverage(
        self,
        draft_fn,
        context: dict[str, Any],
        parser,
        entities: tuple[str, ...],
        traces: list[CallTrace],
        phase: str,
    ) -> Any:
        """Call the draft op, then mechanically verify task-entity coverage of
        the prompt body. On a miss, retry once with an operator correction
        appended outside the projection document. Persistent misses are
        published with a workspace event (utility-first: measurable, not
        fatal)."""
        outcome = draft_fn(context, traces, parser=parser)
        if getattr(outcome, "kind", "") == "TASK_BLOCKED_BY_HIGHER_PRIORITY":
            return outcome
        missing = self._entity_coverage_missing(outcome.prompt_body or "", entities)
        if not missing:
            return outcome
        if self.workspace is not None:
            self.workspace.append_event("TASK_ENTITY_COVERAGE_RETRY", {"missing": len(missing)})
        corrected_context = dict(context)
        corrected_context["SUBSTANTIVE_REQUEST"] = (
            context["SUBSTANTIVE_REQUEST"]
            + "\n\nOPERATOR CORRECTION (host-side mechanical check): the following task entities are "
            "missing from the prompt body and MUST appear verbatim, character-for-character: "
            + "; ".join(missing)
        )
        outcome = draft_fn(corrected_context, traces, parser=parser)
        if getattr(outcome, "kind", "") == "TASK_BLOCKED_BY_HIGHER_PRIORITY":
            return outcome
        missing = self._entity_coverage_missing(outcome.prompt_body or "", entities)
        if missing and self.workspace is not None:
            self.workspace.append_event(
                "TASK_ENTITY_COVERAGE_MISSING",
                {"entities": list(missing), "phase": phase},
            )
        return outcome

    def _draft_initial_prompt(
        self,
        substantive_request: str,
        traces: list[CallTrace],
        *,
        protocol_state: str,
    ) -> EngineResponse:
        assert self.workspace is not None
        self._bound_payload_inputs = _extract_data_payload(substantive_request)
        # Protocol v2: raw content is read by BOOTSTRAP_ANALYSIS only; the
        # compile op receives the sanitized compiled analysis.
        compiled = self._semantic_read(substantive_request, traces)
        if compiled is None:
            self.workspace.append_event("PROTOCOL_BLOCKED", {"phase": "bootstrap"})
            return EngineResponse(presentation.cancelled(), traces, closed=True)
        entities = self._task_entities_cache.get((substantive_request, self._previous_deliverable), ())
        self._active_task_entities = entities

        def _draft_call(ctx: dict[str, Any], tr: list[CallTrace], parser) -> Any:
            return self._call("DRAFT_PROMPT", ctx, tr, parser=parser)

        outcome = self._enforce_entity_coverage(
            _draft_call,
            {
                "HOST_PROTOCOL_STATE": protocol_state,
                "SUBSTANTIVE_REQUEST": compiled,
            },
            self.bridge.parse_prompt_draft,
            entities,
            traces,
            phase="draft_prompt",
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
        # S4 cross-turn chaining (ADR-0008 §4): when the SAME session's prior
        # turn reached a terminal stage and the user issues a new command,
        # continue in the same workspace under the next turn id. Only the prior
        # turn's confirmed deliverable carries forward; drafts, rejected plans,
        # and review dialogue are structurally unreachable in the new turn.
        prior = self.workspace
        if (
            prior is not None
            and prior.turn_id is not None
            and self.controller is not None
            and self.controller.state.stage in {Stage.CLOSED_SUCCESS, Stage.CLOSED_CANCELLED}
        ):
            prior_status = prior.read_turn_status(prior.turn_id).get("status")
            if prior_status == "ACTIVE":
                prior.mark_turn_status(
                    "CLOSED_SUCCESS"
                    if self.controller.state.stage == Stage.CLOSED_SUCCESS
                    else "CLOSED_CANCELLED"
                )
            chained_deliverable = prior.previous_deliverable()
            prior.start_turn(prior.next_turn_id())
            self.workspace = prior
            self._previous_deliverable = chained_deliverable
            self._bound_payload_inputs = None
            self.workspace.append_event(
                "TURN_CHAINED",
                {"turn_id": prior.turn_id, "previous_deliverable": chained_deliverable is not None},
            )
        else:
            self.workspace = self._new_workspace()
            self._previous_deliverable = None
            self._bound_payload_inputs = None
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
        carried = [self._compile_approach_context(s, traces) for s in carried_raw]
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
            # Mechanical coverage regression check on revisions: entities the
            # draft carried must survive revision. Event-only in v1 (no loop).
            missing = self._entity_coverage_missing(body, self._active_task_entities)
            if missing and self.workspace is not None:
                self.workspace.append_event(
                    "TASK_ENTITY_COVERAGE_MISSING",
                    {"entities": list(missing), "phase": "revise_prompt"},
                )
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
                        *map(lambda s: self._compile_approach_context(s, traces), carried_raw),
                        self._compile_approach_context(transition.payload["approach_change_source"], traces),
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
        # quarantine boundary — compile ops never receive unredacted threats.
        supplied_raw = transition.payload.get("execution_input_source") or self._bound_payload_inputs
        if supplied_raw:
            sanitized_payload, _ = compile_bootstrap_output(supplied_raw, supplied_raw)
            supplied_compiled = sanitized_payload.strip()
        else:
            supplied_compiled = None
        # Cross-epoch deliverable chaining (ADR-0008 §4 + ADR-0004): the prior
        # epoch's confirmed deliverable is host-published, gate-passed content
        # (see _semantic_read S4 note). Chain it byte-exact into the execution
        # phase so continuation/revision epochs condition on the actual prior
        # artifact instead of a pseudocode summary. First epochs have no prior
        # deliverable and keep the previous null behavior.
        required_task_inputs = self._previous_deliverable
        # ADR-0009 / TRD-0003 (RS-09, RS-10): feature-gated Result IR mode.
        # Adds structured result-decomposition instructions, chains the prior
        # validated Result IR beside the deliverable, and mechanically
        # validates the emitted IR (coverage + evidence resolution).
        result_ir_mode = os.environ.get("PDLT_RESULT_IR") == "1"
        from pdl_taskmaster.runtime.result_ir import (
            arithmetic_checks,
            derive_requirements,
            entity_enforcement_misses,
            extract_result_ir,
            load_ir_from_deliverable,
            parse_typed_entities,
            render_execution_brief,
            render_instructions,
            render_prior_ir_section,
            validate_result_ir,
        )
        requirements = derive_requirements(prompt_body) if result_ir_mode else []
        execute_context = {
            "CONFIRMED_PROMPT_BODY": prompt_body,
            "CONFIRMED_PLAN_BODY": plan_body,
            "REQUIRED_TASK_INPUTS": required_task_inputs,
            "SUPPLIED_EXECUTION_INPUT_SOURCE": supplied_compiled,
            "AVAILABLE_EXECUTION_TOOLS": self.available_execution_tools,
        }
        if result_ir_mode:
            # TRD-0003: the IR channel rides inside the contract-whitelisted
            # REQUIRED_TASK_INPUTS symbol (adding new symbols would violate the
            # EXECUTION_CONTRACT allow-list). Value = instructions + numbered
            # requirements + (when chained) the prior validated IR.
            evidence_paths = ["execution://body"]
            if self._previous_deliverable and self.workspace.closed_turns():
                closed = [t for t in self.workspace.closed_turns() if t.get("status") == "CLOSED_SUCCESS"]
                if closed:
                    evidence_paths.append(
                        f"turns/{closed[-1]['turn_id']}/stages/50_execution/output/current.md"
                    )
            ir_channel = render_instructions(
                requirements, repo_root=self.repo_root, evidence_paths=evidence_paths
            )
            prior_ir = load_ir_from_deliverable(self._previous_deliverable)
            if prior_ir:
                ir_channel += render_prior_ir_section(prior_ir)
                ir_channel += render_execution_brief(prior_ir, requirements)
            base_inputs = required_task_inputs or ""
            channel_value = (base_inputs + ir_channel) if base_inputs else ir_channel
            # Delivery markers are synthesized BEFORE the draft (4B class): the
            # brief must pin them so the first emission is correctly labeled
            # and no full re-emission is needed.
            declared_names = sorted(
                set(
                    re.findall(
                        r"\b[\w-]+\.(?:py|md|json|txt|cfg|toml)\b",
                        prompt_body + "\n" + plan_body + "\n" + channel_value,
                    )
                )
            )
            marker_entities = tuple(f"### {n}" for n in declared_names)
            if marker_entities:
                channel_value += (
                    "\nDELIVERY FORMAT: file sections MUST be headed exactly by their marker lines "
                    "(e.g. a line reading exactly '### cnf.py' immediately followed by that file's code): "
                    + "; ".join(marker_entities)
                )
            # DRAFT_EXECUTE (ADR-0009): entity extraction at the execute
            # boundary, mirroring DRAFT_PROMPT's task-entity channel. Turns are
            # structurally lossy; the draft declares the verbatim-critical
            # entities (wire formats, constants, signatures) before any code is
            # written, and the host enforces their survival mechanically.
            draft_context = {
                "HOST_PROTOCOL_STATE": "EXECUTION_DRAFT",
                "CONFIRMED_PROMPT_BODY": prompt_body,
                "CONFIRMED_PLAN_BODY": plan_body,
                "REQUIRED_TASK_INPUTS": channel_value,
            }
            draft = self._call(
                "DRAFT_EXECUTE",
                draft_context,
                traces,
                parser=self.bridge.parse_execution_draft,
            )
            # Typed entity pipeline (parser over entities, not string filters):
            # the host classifies, arithmetically validates, and applies
            # kind-appropriate enforcement. meta entities are never enforced
            # against the deliverable.
            typed = parse_typed_entities(draft.execution_entities)
            arithmetic = arithmetic_checks(typed)
            if arithmetic:
                self.workspace.append_event(
                    "EXECUTE_DRAFT_ARITHMETIC_RETRY", {"errors": arithmetic}
                )
                draft_context["REQUIRED_TASK_INPUTS"] = channel_value + (
                    "\n\n\n\nOPERATOR CORRECTION (host-side mechanical check): the declared wire-format "
                    "arithmetic is inconsistent and MUST be fixed before execution: "
                    + " | ".join(arithmetic)
                )
                draft = self._call(
                    "DRAFT_EXECUTE",
                    draft_context,
                    traces,
                    parser=self.bridge.parse_execution_draft,
                )
                typed = parse_typed_entities(draft.execution_entities)
                arithmetic = arithmetic_checks(typed)
                if arithmetic:
                    self.workspace.append_event(
                        "EXECUTE_DRAFT_ARITHMETIC_INVALID",
                        {"errors": arithmetic, "scored": "model_error"},
                    )
            containment_pool = channel_value + prompt_body + plan_body
            kept = [e for e in typed if _norm(e["value"]) in _norm(containment_pool)]
            dropped = len(typed) - len(kept)
            if dropped:
                self.workspace.append_event(
                    "EXECUTE_ENTITY_DROPPED_UNSAFE", {"count": dropped}
                )
            # Delivery markers are always enforced entities (4B class): the
            # section headers themselves are lossy across turns.
            declared_names = sorted(
                set(
                    re.findall(
                        r"[\w-]+\.(?:py|md|json|txt|cfg|toml)",
                        prompt_body + " " + plan_body + " " + channel_value,
                    )
                )
            )
            existing_values = {e["value"] for e in kept}
            kept = kept + [
                {"kind": "delivery_marker", "value": f"### {n}", "name": None,
                 "struct_format": None, "declared_size": None}
                for n in declared_names
                if f"### {n}" not in existing_values
            ]
            brief_misses, _ = entity_enforcement_misses(kept, draft.brief_body, None)
            if brief_misses:
                self.workspace.append_event(
                    "EXECUTE_ENTITY_COVERAGE_RETRY", {"missing": len(brief_misses)}
                )
                draft_context["REQUIRED_TASK_INPUTS"] = channel_value + (
                    "\n\n\n\nOPERATOR CORRECTION (host-side mechanical check): the following execution "
                    "entities are missing from the brief body and MUST appear verbatim, "
                    "character-for-character: " + " | ".join(brief_misses)
                )
                draft = self._call(
                    "DRAFT_EXECUTE",
                    draft_context,
                    traces,
                    parser=self.bridge.parse_execution_draft,
                )
            entity_block = (
                "\n## EXECUTION BRIEF (entity-dense; drafted prior to execution)\n"
                + draft.brief_body
                + "\nCRITICAL VERBATIM ENTITIES (each MUST appear verbatim in the deliverable; "
                "the host checks this mechanically):\n"
                + "\n" + "\n".join(f"- [{e['kind']}] {e['value']}]" for e in kept)
                + "\nDELIVERY FORMAT: file sections MUST be headed exactly by their marker lines "
                "(e.g. a line reading exactly '### cnf.py' immediately followed by that file's code)."
            )
            execute_context["REQUIRED_TASK_INPUTS"] = (
                (base_inputs + entity_block + ir_channel) if base_inputs else (entity_block + ir_channel)
            )
            execute_entities = kept
        else:
            execute_entities = ()
        outcome = self._call(
            "EXECUTE",
            execute_context,
            traces,
            parser=self.bridge.parse_execution,
        )
        final_body = outcome.body
        if result_ir_mode and outcome.kind == "RESULT":
            workspace_path = self.workspace.path
            attempts = 0
            repaired = False
            while True:
                wire_ir = getattr(outcome, "result_ir", None)
                if isinstance(wire_ir, dict):
                    # Option 2 (ADR-0009): the IR arrived as a schema-enforced
                    # wire field; body scanning is only the recorded-path
                    # fallback.
                    ir = wire_ir
                else:
                    ir = extract_result_ir(final_body)
                if ir is not None:
                    ir_errors, _ = validate_result_ir(
                        ir, workspace_path, requirements, execution_body=final_body
                    )
                else:
                    ir_errors = ["Result IR missing or not a JSON object (TRD-0003 RS-01)"]
                _, entity_missing = entity_enforcement_misses(
                    execute_entities, "", final_body
                )
                if entity_missing:
                    self.workspace.append_event(
                        "EXECUTE_ENTITY_MISSING", {"count": len(entity_missing)}
                    )
                errors = ir_errors + [
                    f"critical execution entity missing from the deliverable: {e!r}" for e in entity_missing
                ]
                if not errors or attempts >= 2:
                    break
                attempts += 1
                if not entity_missing:
                    # IR-only repair (TRD-0003 RS-08): a dedicated
                    # schema-enforced repair op re-emits ONLY the corrected
                    # result_ir, so the retry budget affords multiple cheap
                    # attempts instead of one full re-emission.
                    repair_ctx = {
                        "HOST_PROTOCOL_STATE": "RESULT_IR_REPAIR",
                        "DELIVERABLE_BODY": final_body,
                        "RESULT_IR_REQUIREMENTS": render_instructions(
                            requirements,
                            repo_root=self.repo_root,
                            evidence_paths=evidence_paths,
                        ),
                        "RESULT_IR_ERRORS": " | ".join(ir_errors),
                    }
                    repair = self._call(
                        "EMIT_RESULT_IR",
                        repair_ctx,
                        traces,
                        parser=self.bridge.parse_result_ir_repair,
                    )
                    ir2 = repair.get("result_ir") if isinstance(repair, dict) else None
                    if ir2 is not None:
                        e2, _ = validate_result_ir(
                            ir2, workspace_path, requirements, execution_body=final_body
                        )
                        if not e2:
                            fence_open = "\n\n```json\n"
                            fence_close = "\n```"
                            final_body = (
                                final_body
                                + "\n\n"
                                + fence_open
                                + json.dumps(ir2, indent=2, ensure_ascii=False)
                                + fence_close
                            )
                            repaired = True
                            self.workspace.append_event(
                                "RESULT_IR_REPAIRED", {"attempts": attempts}
                            )
                            break
                        ir_errors = e2
                    self.workspace.append_event(
                        "RESULT_IR_REPAIR_RETRY", {"attempt": attempts}
                    )
                    continue
                # Code-defect retry: the deliverable itself is wrong; a full
                # re-emission is unavoidable (option 2: body + IR travel
                # together under the wire schema).
                correction_ctx = dict(execute_context)
                correction_ctx["REQUIRED_TASK_INPUTS"] = execute_context["REQUIRED_TASK_INPUTS"] + (
                    "\\n\\nRESULT IR VALIDATION ERRORS (host-side mechanical check): fix ONLY these violations and re-emit the FULL response with a corrected result_ir: "
                    + " | ".join(errors)
                )
                outcome = self._call(
                    "EXECUTE",
                    correction_ctx,
                    traces,
                    parser=self.bridge.parse_execution,
                )
                final_body = outcome.body
            if repaired:
                self.workspace.append_event(
                    "RESULT_IR_VALIDATED", {"ir": ir, "repaired": True}
                )
            elif errors:
                self.workspace.append_event(
                    "RESULT_IR_INVALID", {"errors": errors, "scored": "model_error"}
                )
            else:
                self.workspace.append_event("RESULT_IR_VALIDATED", {"ir": ir})
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
        result_body_hash = hashlib.sha256(final_body.encode("utf-8")).hexdigest()
        self.controller.complete_success(result_body_hash)
        if self.workspace.turn_id is not None:
            self.workspace.mark_turn_status("CLOSED_SUCCESS", deliverable_sha256=result_body_hash)
        self.workspace.publish_execution_outcome(
            outcome.kind,
            final_body,
            {
                "source_prompt_id": prompt.artifact_id,
                "source_plan_id": plan.artifact_id,
                "result_body_hash": result_body_hash,
                "confirmed_prompt_hash": hashlib.sha256(prompt.body.encode("utf-8")).hexdigest(),
                "confirmed_plan_hash": hashlib.sha256(plan.body.encode("utf-8")).hexdigest(),
            },
        )
        return EngineResponse(final_body, traces, closed=True)

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

    def handle_explicit_review(self, intent: Intent, feedback: str | None = None) -> EngineResponse:
        """Directly apply a review intent without LLM interpretation overhead (fast-path)."""
        traces: list[CallTrace] = []
        if self.workspace is None:
            raise WorkspaceError("active_controller_without_workspace")
        if self.controller is None:
            raise ControllerError("user_message_stage")
        # Durability (ADR-0009 workflow): interrupted internal transitions are
        # re-driven by explicit user input instead of bricking the epoch.
        if self.controller.state.stage == Stage.PLAN_REQUIRED:
            return self._draft_plan(Transition(NextAction.DRAFT_PLAN, {}), traces)
        if self.controller.state.stage == Stage.EXECUTION_READY:
            return self._execute(Transition(NextAction.EXECUTE, {}), traces)
        if self.controller.state.stage not in {Stage.PROMPT_REVIEW, Stage.PLAN_REVIEW, Stage.WAITING_INPUT}:
            raise ControllerError("user_message_stage")

        self._sync_review_edit()
        previous_stage = self.controller.state.stage
        decision = ReviewDecision(intent=intent)
        msg = feedback or ""
        transition = self.controller.apply_review_decision(decision, msg)
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
        return self._apply_transition(transition, msg, traces)

    def handle_user_message(self, user_message: str) -> EngineResponse:
        traces: list[CallTrace] = []
        if self.controller is None or self.controller.state.stage in {Stage.CLOSED_SUCCESS, Stage.CLOSED_CANCELLED}:
            return self._activation(user_message, traces) or EngineResponse(None, traces, bypass=True)

        if self.workspace is None:
            raise WorkspaceError("active_controller_without_workspace")
        # Durability (ADR-0009 workflow): interrupted internal transitions are
        # re-driven by any user input instead of bricking the epoch.
        if self.controller.state.stage == Stage.PLAN_REQUIRED:
            return self._draft_plan(Transition(NextAction.DRAFT_PLAN, {}), traces)
        if self.controller.state.stage == Stage.EXECUTION_READY:
            return self._execute(Transition(NextAction.EXECUTE, {}), traces)
        if self.controller.state.stage not in {Stage.PROMPT_REVIEW, Stage.PLAN_REVIEW, Stage.WAITING_INPUT}:
            raise ControllerError("user_message_stage")

        stripped = user_message.strip()
        # Silence-deferral fix (Finding D3): do not route empty/whitespace input to LLM interpretation
        if not stripped:
            artifact_name = "prompt pseudocode" if self.controller.state.stage == Stage.PROMPT_REVIEW else "execution plan"
            return EngineResponse(
                f"Please confirm the {artifact_name} (type /confirm or press Enter with confirmation) or specify revisions (/revise <feedback>).",
                traces,
            )

        # Fast-path commands
        lower = stripped.lower()
        if lower in {
            "/confirm", "confirm", "yes", "y", "proceed",
            "looks good", "lgtm", "approved", "ok", "okay", "accept",
        }:
            return self.handle_explicit_review(Intent.ACCEPT_CURRENT)
        if lower.startswith("/revise"):
            fb = stripped[7:].strip()
            if not fb:
                return EngineResponse("Please specify your revisions: /revise <feedback>", traces)
            target_intent = (
                Intent.REVISE_TASK
                if self.controller.state.stage == Stage.PROMPT_REVIEW
                else Intent.REVISE_APPROACH
            )
            return self.handle_explicit_review(target_intent, fb)
        if lower in {"/stop", "stop", "/cancel", "cancel"}:
            return self.handle_explicit_review(Intent.CANCEL)

        # Standard LLM review interpretation
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
