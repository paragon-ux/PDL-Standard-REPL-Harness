from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

from observation.session import ObservedSession
from observation.records import controller_snapshot
from observation.sink import JsonlSink


@dataclass
class HostTurn:
    text: str | None
    bypass: bool
    closed: bool
    state_after: dict[str, Any] | None


@dataclass
class _PlainRequest:
    prompt: str
    operation: str = "BYPASS_ORDINARY"


class PDLtHost:
    """External interactive host.

    The host owns process/session lifetime only. Protocol state remains in
    SessionEngine/Workspace; /status is a read-only projection.
    """

    def __init__(
        self,
        candidate_repo: str | Path,
        *,
        worker: Any,
        workspace_root: str | Path | None = None,
        restore_path: str | Path | None = None,
        run_id: str = "host",
        case_id: str | None = None,
        observation_dir: str | Path | None = None,
        include_bodies: bool = False,
    ):
        self.candidate_repo = Path(candidate_repo).resolve()
        self.worker = worker
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd() / "runs" / "workspaces"
        self.restore_path = Path(restore_path) if restore_path else None
        self.run_id = run_id
        self.case_id = case_id
        self.observation_dir = Path(observation_dir) if observation_dir else None
        self.include_bodies = include_bodies
        self.engine: Any = None
        self.observed: ObservedSession | None = None
        self.sink: JsonlSink | None = None

    def _load_candidate(self) -> None:
        repo = str(self.candidate_repo)
        if repo not in sys.path:
            sys.path.insert(0, repo)

    def start(self) -> "PDLtHost":
        self._load_candidate()
        from runtime.session_engine import SessionEngine

        if self.restore_path is not None:
            engine = SessionEngine.restore(
                str(self.candidate_repo),
                lambda request: "",
                self.restore_path,
                higher_priority_constraints="Obey applicable provider/platform safety, privacy, permission, and tool constraints.",
                available_execution_tools=[],
            )
        else:
            engine = SessionEngine(
                str(self.candidate_repo),
                lambda request: "",
                higher_priority_constraints="Obey applicable provider/platform safety, privacy, permission, and tool constraints.",
                available_execution_tools=[],
                workspace_root=self.workspace_root,
            )
        self.engine = engine
        if self.observation_dir is not None:
            session_id = f"{self.run_id}-{self.case_id or 'session'}"
            self.sink = JsonlSink(self.observation_dir, session_id)
        self.observed = ObservedSession(
            engine,
            self.sink,
            run_id=self.run_id,
            case_id=self.case_id,
            include_bodies=self.include_bodies,
            worker=self.worker,
        )
        return self

    def handle(self, user_message: str) -> HostTurn:
        if self.observed is None:
            raise RuntimeError("host not started")
        routed_message = self._ensure_protocol_entry(user_message)
        response = self.observed.handle_user_message(routed_message)
        if response.bypass and response.text is None:
            plain = self.worker.call(_PlainRequest(user_message))
            return HostTurn(
                text=plain.text,
                bypass=True,
                closed=False,
                state_after=controller_snapshot(self.engine),
            )
        return HostTurn(
            text=response.text,
            bypass=bool(response.bypass),
            closed=bool(response.closed),
            state_after=controller_snapshot(self.engine),
        )

    def _ensure_protocol_entry(self, user_message: str) -> str:
        if self.engine is None or self.engine.controller is None:
            return self._with_invocation(user_message)
        stage = self.engine.controller.state.stage.value
        if stage in {"CLOSED_SUCCESS", "CLOSED_CANCELLED"}:
            return self._with_invocation(user_message)
        return user_message

    @staticmethod
    def _with_invocation(user_message: str) -> str:
        if "$confirm-with-pseudocode" in user_message:
            return user_message
        return "$confirm-with-pseudocode " + user_message

    def status(self) -> dict[str, Any]:
        if self.engine is None:
            return {"active": False}
        state = self.engine.controller.state.to_dict() if self.engine.controller is not None else None
        return {
            "active": True,
            "workspace_id": self.engine.workspace.metadata.get("workspace_id") if self.engine.workspace else None,
            "workspace_path": str(self.engine.workspace.path) if self.engine.workspace else None,
            "controller_state": state,
        }

    def close(self) -> None:
        if self.sink is not None:
            self.sink.close()
