from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import time
import tempfile

from observation.parsers import parse_operation_output
from observation.records import (
    controller_snapshot,
    event_delta,
    read_events,
    sha256_json,
    sha256_text,
    utcnow,
)
from observation.sink import JsonlSink


class ObservedSession:
    """Wrap SessionEngine without becoming a second semantic participant.

    Parsed facts are derived after the engine returns, using a disposable
    OperationBridge. Observer failures are recorded and never change the
    protocol result.
    """

    def __init__(
        self,
        engine: Any,
        sink: JsonlSink | None = None,
        *,
        run_id: str = "unset",
        case_id: str | None = None,
        include_bodies: bool = False,
        worker: Any | None = None,
    ):
        self.engine = engine
        self.sink = sink
        self.run_id = run_id
        self.case_id = case_id
        self.include_bodies = include_bodies
        self.turn_index = 0
        self.calls: list[dict[str, Any]] = []
        self._worker = worker
        self._original_model_call = engine.model_call
        engine.model_call = self._observed_model_call

    @property
    def session_id(self) -> str:
        if self.engine.workspace is not None:
            return str(self.engine.workspace.metadata.get("workspace_id", "workspace"))
        return "session"

    def _observed_model_call(self, request: Any) -> str:
        started = time.perf_counter()
        metadata: dict[str, Any] = {}
        if self._worker is not None:
            result = self._worker.call(request)
            raw_text = result.text
            metadata = dict(result.metadata or {})
        else:
            raw_text = self._original_model_call(request)
        latency_ms = (time.perf_counter() - started) * 1000.0
        call = {
            "operation": request.operation,
            "workspace_stage": request.workspace_invocation.stage,
            "workspace_invocation_id": request.workspace_invocation.invocation_id,
            "projection_manifest_sha256": sha256_json(request.manifest),
            "prompt_sha256": sha256_text(request.prompt),
            "response_sha256": sha256_text(raw_text),
            "raw_text": raw_text,
            "response_id": metadata.get("response_id"),
            "observed_model": metadata.get("observed_model"),
            "usage": metadata.get("usage"),
            "latency_ms": metadata.get("latency_ms", latency_ms),
            "raw_meta": metadata.get("raw_meta"),
        }
        self.calls.append(call)
        return raw_text

    def handle_user_message(self, user_message: str) -> Any:
        before = controller_snapshot(self.engine)
        events_before = read_events(self.engine.workspace)
        call_start = len(self.calls)
        started = time.perf_counter()
        exception: dict[str, Any] | None = None
        response = None
        try:
            response = self.engine.handle_user_message(user_message)
        except Exception as exc:
            exception = {"type": type(exc).__name__, "message": str(exc)}
        wall_ms = (time.perf_counter() - started) * 1000.0
        after = controller_snapshot(self.engine)
        events_after = read_events(self.engine.workspace)
        new_calls = self.calls[call_start:]
        parsed_calls: list[dict[str, Any]] = []
        observer_analysis_errors: list[str] = []
        for call in new_calls:
            parsed, parse_error = parse_operation_output(
                self.engine.repo_root,
                call["operation"],
                call["raw_text"],
            )
            if parse_error is not None:
                observer_analysis_errors.append(
                    f"{call['operation']}:{parse_error}"
                )
            public_call = {
                "operation": call["operation"],
                "workspace_stage": call["workspace_stage"],
                "workspace_invocation_id": call["workspace_invocation_id"],
                "projection_manifest_sha256": call["projection_manifest_sha256"],
                "prompt_sha256": call["prompt_sha256"],
                "response_sha256": call["response_sha256"],
                "response_id": call["response_id"],
                "observed_model": call["observed_model"],
                "usage": call["usage"],
                "latency_ms": call["latency_ms"],
                "raw_meta": call["raw_meta"],
                "parsed": parsed,
                "parse_error": parse_error,
            }
            if self.include_bodies:
                public_call["raw_text"] = call["raw_text"]
            parsed_calls.append(public_call)

        response_record: dict[str, Any] = {}
        if response is not None:
            response_record = {
                "bypass": bool(getattr(response, "bypass", False)),
                "closed": bool(getattr(response, "closed", False)),
                "text_sha256": sha256_text(response.text or "") if response.text is not None else None,
                "text_length": len(response.text or "") if response.text is not None else 0,
            }
            if self.include_bodies and response.text is not None:
                response_record["text"] = response.text

        record = {
            "schema": 1,
            "at_utc": utcnow(),
            "run_id": self.run_id,
            "case_id": self.case_id,
            "session_id": self.session_id,
            "workspace_id": after["workspace_id"] if after else None,
            "workspace_path": after["workspace_path"] if after else None,
            "turn_index": self.turn_index + 1,
            "user_message_sha256": sha256_text(user_message),
            "controller_before": before,
            "controller_after": after,
            "response": response_record,
            "calls": parsed_calls,
            "events": event_delta(events_before, events_after),
            "exception": exception,
            "observer_analysis_error": observer_analysis_errors or None,
            "wall_ms": wall_ms,
        }
        if self.sink is not None:
            self.sink.record(record)
        self.turn_index += 1
        if exception is not None:
            raise RuntimeError(f"{exception['type']}: {exception['message']}")
        return response

    @classmethod
    def restore(
        cls,
        candidate_repo: str | Path,
        workspace_path: str | Path,
        sink: JsonlSink | None = None,
        *,
        worker: Any | None = None,
        run_id: str = "unset",
        case_id: str | None = None,
        include_bodies: bool = False,
        **engine_kwargs: Any,
    ) -> "ObservedSession":
        import sys

        repo = str(Path(candidate_repo).resolve())
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from runtime.session_engine import SessionEngine

        engine = SessionEngine.restore(repo, lambda request: "", workspace_path, **engine_kwargs)
        return cls(engine, sink, run_id=run_id, case_id=case_id, include_bodies=include_bodies, worker=worker)

    @classmethod
    def create(
        cls,
        candidate_repo: str | Path,
        worker: Any,
        *,
        workspace_root: str | Path | None = None,
        sink: JsonlSink | None = None,
        run_id: str = "live",
        case_id: str | None = None,
        include_bodies: bool = False,
        higher_priority_constraints: Any = "Obey applicable provider/platform safety, privacy, permission, and tool constraints.",
        available_execution_tools: Any = None,
    ) -> "ObservedSession":
        """Create an observed session on a fresh workspace with arbitrary input."""
        import sys

        repo = str(Path(candidate_repo).resolve())
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from runtime.session_engine import SessionEngine

        if workspace_root is None:
            workspace_root = tempfile.mkdtemp(prefix="pdl-r2s-live-")
        engine = SessionEngine(
            repo,
            lambda request: "",
            higher_priority_constraints=higher_priority_constraints,
            available_execution_tools=available_execution_tools or [],
            workspace_root=workspace_root,
        )
        return cls(engine, sink, run_id=run_id, case_id=case_id, include_bodies=include_bodies, worker=worker)
