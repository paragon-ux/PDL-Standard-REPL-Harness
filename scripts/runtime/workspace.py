from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import re
import tempfile
import uuid


class WorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceInvocation:
    operation: str
    stage: str
    invocation_id: str
    input_dir: Path
    output_dir: Path


class WorkspaceRun:
    """Filesystem-backed ICM context-flow workspace for one candidate session.

    The workspace is an orchestration and handoff substrate only. It does not
    define protocol correctness. Standard Contracts remain the sole normative
    authority; the Execution Contract selects which Standard IDs and working
    artifacts are exposed to each semantic operation.
    """

    SCHEMA = "C0-ICM-WORKSPACE-5"

    def __init__(self, repo_root: Path, path: Path):
        self.repo_root = repo_root
        self.path = path
        self.metadata_path = self.path / "workspace.json"
        if not self.metadata_path.is_file():
            raise WorkspaceError("workspace_metadata_missing")
        self.metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        if self.metadata.get("schema_version") != self.SCHEMA:
            raise WorkspaceError("workspace_schema")
        # Session-hierarchy mode (ADR-0008 / Phase 9 S3): when turn_id is set,
        # turn-scoped state (controller state, events, stages) lives under
        # turns/<turn_id>/ while shared/ and workspace.json stay session-level.
        # Legacy single-turn workspaces (turn_id None) keep the flat layout.
        self.turn_id: str | None = self.metadata.get("turn_id")
        from scripts.runtime.normative_store import NormativeStore
        contract_path = NormativeStore.resolve_contract(self.repo_root, "EXECUTION_CONTRACT.json")
        if not contract_path.is_file():
            contract_path = self.repo_root / "contracts" / "EXECUTION_CONTRACT.json"
        self.execution_contract = json.loads(contract_path.read_text(encoding="utf-8"))

    @classmethod
    def create(
        cls,
        repo_root: str | Path,
        workspace_root: str | Path,
        *,
        turn_id: str | None = None,
    ) -> "WorkspaceRun":
        repo_root = Path(repo_root)
        workspace_root = Path(workspace_root)
        workspace_root.mkdir(parents=True, exist_ok=True)
        workspace_id = f"W-{uuid.uuid4().hex[:12]}"
        path = workspace_root / workspace_id
        if path.exists():
            raise WorkspaceError("workspace_collision")
        path.mkdir(parents=True, exist_ok=True)
        if turn_id is None:
            (path / "state").mkdir(exist_ok=True)
            (path / "events").mkdir(exist_ok=True)
            (path / "stages").mkdir(exist_ok=True)
            (path / "shared").mkdir(exist_ok=True)
        else:
            # Session-hierarchy mode (S3): session-level dirs plus the first
            # turn's scoped tree. Stage directories materialize on demand.
            (path / "shared").mkdir(exist_ok=True)
            cls._scaffold_turn(path, turn_id)
        metadata = {
            "schema_version": cls.SCHEMA,
            "workspace_id": workspace_id,
            "protocol_instance_id": None,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "icm_reference": "arXiv:2603.16021v2",
            "context_flow": "filesystem_stage_handoffs",
            "control_flow": "mechanical_controller",
        }
        if turn_id is not None:
            metadata["turn_id"] = turn_id
            metadata["session_hierarchy"] = True
        cls._atomic_write(path / "workspace.json", json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        run = cls(repo_root, path)
        run.append_event("WORKSPACE_CREATED", {"workspace_id": workspace_id, "turn_id": turn_id})
        return run

    @classmethod
    def _scaffold_turn(cls, path: Path, turn_id: str) -> Path:
        turn_dir = path / "turns" / turn_id
        if turn_dir.exists():
            raise WorkspaceError(f"turn_exists:{turn_id}")
        (turn_dir / "state").mkdir(parents=True, exist_ok=False)
        (turn_dir / "events").mkdir(parents=True, exist_ok=False)
        (turn_dir / "stages").mkdir(parents=True, exist_ok=False)
        cls._atomic_write(
            turn_dir / "turn.json",
            json.dumps(
                {
                    "turn_id": turn_id,
                    "status": "ACTIVE",
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        return turn_dir

    # -- Session-hierarchy helpers (S3/S4) ---------------------------------

    def _turn_base(self) -> Path:
        """Root for turn-scoped state: turns/<turn_id> in hierarchy mode,
        the workspace root in legacy flat mode."""
        return self.path / "turns" / self.turn_id if self.turn_id else self.path

    def stages_root(self) -> Path:
        """Public root for this workspace's stage tree (turn-scoped in
        hierarchy mode; workspace root in legacy flat mode). Readers that
        walk stage output must use this instead of path/"stages" so both
        layouts stay supported."""
        return self._turn_base() / "stages"

    def start_turn(self, new_turn_id: str) -> None:
        """Open a new turn in this session workspace and move the pointer.

        The prior turn's scoped state (controller state, events, stages) is
        preserved verbatim; only the pointer moves. Per ADR-0008 S4, the new
        turn starts clean: prior drafts, rejected plans, and review dialogue
        are never carried forward except through previous_deliverable()."""
        if self.turn_id is None:
            raise WorkspaceError("session_hierarchy_required")
        if new_turn_id == self.turn_id:
            raise WorkspaceError("turn_pointer_unchanged")
        self._scaffold_turn(self.path, new_turn_id)
        self.metadata["turn_id"] = new_turn_id
        self._atomic_write(
            self.metadata_path,
            json.dumps(self.metadata, ensure_ascii=False, indent=2) + "\n",
        )
        self.turn_id = new_turn_id

    def read_turn_status(self, turn_id: str) -> dict[str, Any]:
        path = self.path / "turns" / turn_id / "turn.json"
        if not path.is_file():
            raise WorkspaceError(f"turn_missing:{turn_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def mark_turn_status(self, status: str, *, deliverable_sha256: str | None = None) -> None:
        if self.turn_id is None:
            raise WorkspaceError("session_hierarchy_required")
        path = self.path / "turns" / self.turn_id / "turn.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"turn_id": self.turn_id}
        data["status"] = status
        if deliverable_sha256 is not None:
            data["deliverable_sha256"] = deliverable_sha256
        data["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        self._atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        self.append_event("TURN_STATUS", {"turn_id": self.turn_id, "status": status})

    def next_turn_id(self) -> str:
        """Next free turn identifier (turn_001, turn_002, ...) for this workspace."""
        turns_dir = self.path / "turns"
        highest = 0
        if turns_dir.is_dir():
            for turn_dir in turns_dir.iterdir():
                m = re.match(r"^turn_(\d+)$", turn_dir.name)
                if m:
                    highest = max(highest, int(m.group(1)))
        return f"turn_{highest + 1:03d}"

    def closed_turns(self) -> list[dict[str, Any]]:
        """All turns with a terminal status, in turn order."""
        turns_dir = self.path / "turns"
        if not turns_dir.is_dir():
            return []
        out = []
        for turn_dir in sorted(turns_dir.iterdir()):
            marker = turn_dir / "turn.json"
            if marker.is_file():
                data = json.loads(marker.read_text(encoding="utf-8"))
                if data.get("status") in {"CLOSED_SUCCESS", "CLOSED_CANCELLED"}:
                    out.append(data)
        return out

    def previous_deliverable(self) -> str | None:
        """S4: the confirmed deliverable of the most recent CLOSED_SUCCESS turn.

        Reads ONLY that turn's published execution artifact
        (turns/<id>/stages/50_execution/output/current.md). Drafts, rejected
        plans, and review dialogue are structurally unreachable from here.
        Returns None when no prior turn has closed successfully."""
        closed = [t for t in self.closed_turns() if t.get("status") == "CLOSED_SUCCESS"]
        if not closed:
            return None
        turn_id = closed[-1].get("turn_id")
        body = self.path / "turns" / str(turn_id) / "stages" / "50_execution" / "output" / "current.md"
        if not body.is_file():
            return None
        return body.read_text(encoding="utf-8").rstrip("\n")

    @classmethod
    def open(cls, repo_root: str | Path, path: str | Path) -> "WorkspaceRun":
        return cls(Path(repo_root), Path(path))

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _serialize_symbol(value: Any) -> tuple[str, str]:
        if isinstance(value, str):
            return ".md", value.rstrip() + "\n"
        return ".json", json.dumps(value, ensure_ascii=False, indent=2) + "\n"

    @staticmethod
    def _deserialize_symbol(path: Path) -> Any:
        if path.suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        return path.read_text(encoding="utf-8").rstrip("\n")

    def append_event(self, kind: str, payload: dict[str, Any]) -> None:
        event = {
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "payload": payload,
        }
        events = self._turn_base() / "events" / "events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        with events.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @property
    def controller_state_path(self) -> Path:
        return self._turn_base() / "state" / "controller-state.json"

    @property
    def protocol_instance_id(self) -> str | None:
        value = self.metadata.get("protocol_instance_id")
        return value if isinstance(value, str) else None

    def bind_protocol(self, instance_id: str) -> None:
        current = self.protocol_instance_id
        if self.turn_id is not None:
            # Session-hierarchy mode: each turn runs its own protocol lifecycle,
            # so re-binding across turns is expected. Record the instance on
            # the current turn; the root pointer tracks the latest binding.
            turn_json = self.path / "turns" / self.turn_id / "turn.json"
            data = json.loads(turn_json.read_text(encoding="utf-8")) if turn_json.is_file() else {"turn_id": self.turn_id}
            data["protocol_instance_id"] = instance_id
            self._atomic_write(turn_json, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            self.metadata["protocol_instance_id"] = instance_id
            self._atomic_write(
                self.metadata_path,
                json.dumps(self.metadata, ensure_ascii=False, indent=2) + "\n",
            )
            self.append_event("PROTOCOL_BOUND", {"instance_id": instance_id, "turn_id": self.turn_id})
            return
        if current is not None and current != instance_id:
            raise WorkspaceError("workspace_already_bound")
        self.metadata["protocol_instance_id"] = instance_id
        self._atomic_write(
            self.metadata_path,
            json.dumps(self.metadata, ensure_ascii=False, indent=2) + "\n",
        )
        self.append_event("PROTOCOL_BOUND", {"instance_id": instance_id})

    def _stage_for(self, operation: str, values: dict[str, Any]) -> str:
        try:
            spec = self.execution_contract["operations"][operation]
        except KeyError as exc:
            raise WorkspaceError(f"operation:{operation}") from exc
        stage = spec.get("workspace_stage")
        selectors = spec.get("workspace_stage_by")
        if selectors:
            symbol = selectors.get("symbol")
            mapping = selectors.get("mapping", {})
            selected = mapping.get(values.get(symbol))
            if not selected:
                raise WorkspaceError(f"stage_selector:{operation}:{values.get(symbol)}")
            stage = selected
        stage_dir = self._turn_base() / "stages" / stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        return stage

    def _next_invocation_id(self, stage: str, operation: str) -> str:
        counter_path = self._turn_base() / "state" / "invocation-counter.json"
        if counter_path.is_file():
            value = json.loads(counter_path.read_text(encoding="utf-8"))
            counter = int(value.get("counter", 0)) + 1
        else:
            counter = 1
        self._atomic_write(counter_path, json.dumps({"counter": counter}, indent=2) + "\n")
        return f"{counter:04d}-{operation.lower()}"

    def materialize_operation(
        self,
        operation: str,
        values: dict[str, Any],
        *,
        higher_priority_constraints: Any = None,
    ) -> WorkspaceInvocation:
        stage = self._stage_for(operation, values)
        invocation_id = self._next_invocation_id(stage, operation)
        stage_path = self._turn_base() / "stages" / stage
        input_dir = stage_path / "input" / invocation_id
        output_dir = stage_path / "output" / invocation_id
        input_dir.mkdir(parents=True, exist_ok=False)
        output_dir.mkdir(parents=True, exist_ok=False)

        index: dict[str, str] = {}
        for symbol, value in values.items():
            suffix, content = self._serialize_symbol(value)
            filename = symbol.lower() + suffix
            self._atomic_write(input_dir / filename, content)
            index[symbol] = filename
        if higher_priority_constraints is not None:
            suffix, content = self._serialize_symbol(higher_priority_constraints)
            filename = "higher_priority_constraints" + suffix
            self._atomic_write(input_dir / filename, content)
            index["HIGHER_PRIORITY_CONSTRAINTS"] = filename
        self._atomic_write(input_dir / "index.json", json.dumps(index, ensure_ascii=False, indent=2) + "\n")
        self._atomic_write(
            input_dir / "invocation.json",
            json.dumps(
                {
                    "operation": operation,
                    "stage": stage,
                    "invocation_id": invocation_id,
                    "input_symbols": list(values),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        self.append_event(
            "OPERATION_MATERIALIZED",
            {"operation": operation, "stage": stage, "invocation_id": invocation_id},
        )
        return WorkspaceInvocation(operation, stage, invocation_id, input_dir, output_dir)

    def load_operation_values(self, invocation: WorkspaceInvocation) -> tuple[dict[str, Any], Any]:
        index = json.loads((invocation.input_dir / "index.json").read_text(encoding="utf-8"))
        values: dict[str, Any] = {}
        higher_priority = None
        for symbol, filename in index.items():
            value = self._deserialize_symbol(invocation.input_dir / filename)
            if symbol == "HIGHER_PRIORITY_CONSTRAINTS":
                higher_priority = value
            else:
                values[symbol] = value
        return values, higher_priority

    def record_projection(self, invocation: WorkspaceInvocation, manifest: dict[str, Any], document: dict[str, Any]) -> None:
        self._atomic_write(
            invocation.output_dir / "projection-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        self._atomic_write(
            invocation.output_dir / "compiled-projection.json",
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        )

    def record_model_output(self, invocation: WorkspaceInvocation, model_text: str) -> None:
        self._atomic_write(invocation.output_dir / "model-response.txt", model_text.rstrip() + "\n")
        self.append_event(
            "MODEL_OUTPUT_RECORDED",
            {"operation": invocation.operation, "stage": invocation.stage, "invocation_id": invocation.invocation_id},
        )

    def record_parsed_output(self, invocation: WorkspaceInvocation, value: Any) -> None:
        self._atomic_write(
            invocation.output_dir / "parsed-output.json",
            json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        )

    def _artifact_stage(self, kind: str) -> Path:
        if kind == "prompt":
            return self._turn_base() / "stages" / "10_prompt" / "output"
        if kind == "plan":
            return self._turn_base() / "stages" / "30_plan" / "output"
        if kind == "result":
            return self._turn_base() / "stages" / "50_execution" / "output"
        raise WorkspaceError(f"artifact_kind:{kind}")

    def publish_artifact(self, kind: str, artifact_id: str, body: str, *, confirmed: bool, source_prompt_id: str | None = None, confirmed_prompt_hash: str | None = None) -> None:
        output = self._artifact_stage(kind)
        versions = output / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        self._atomic_write(versions / f"{artifact_id}.md", body.rstrip() + "\n")
        self._atomic_write(output / "current.md", body.rstrip() + "\n")
        payload: dict[str, Any] = {
            "artifact_id": artifact_id,
            "confirmed": confirmed,
            "source_prompt_id": source_prompt_id,
        }
        if confirmed_prompt_hash:
            payload["confirmed_prompt_hash"] = confirmed_prompt_hash
        self._atomic_write(output / "current.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self.append_event(
            "ARTIFACT_PUBLISHED",
            {"kind": kind, "artifact_id": artifact_id, "confirmed": confirmed},
        )

    def invalidate_artifact(self, kind: str, reason: str) -> None:
        output = self._artifact_stage(kind)
        meta_path = output / "current.json"
        body_path = output / "current.md"
        if not meta_path.is_file() or not body_path.is_file():
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        artifact_id = meta.get("artifact_id")
        invalidated = output / "invalidated"
        invalidated.mkdir(parents=True, exist_ok=True)
        self._atomic_write(
            invalidated / f"{artifact_id}.json",
            json.dumps({**meta, "status": "invalidated", "reason": reason}, ensure_ascii=False, indent=2) + "\n",
        )
        meta_path.unlink()
        body_path.unlink()
        self.append_event("ARTIFACT_INVALIDATED", {"kind": kind, "artifact_id": artifact_id, "reason": reason})

    def mark_artifact_confirmed(self, kind: str, artifact_id: str) -> None:
        output = self._artifact_stage(kind)
        meta_path = output / "current.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("artifact_id") != artifact_id:
            raise WorkspaceError("artifact_confirmation_identity")
        meta["confirmed"] = True
        self._atomic_write(meta_path, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        self.append_event("ARTIFACT_CONFIRMED", {"kind": kind, "artifact_id": artifact_id})

    def read_artifact(self, kind: str) -> tuple[dict[str, Any], str]:
        output = self._artifact_stage(kind)
        meta_path = output / "current.json"
        body_path = output / "current.md"
        if not meta_path.is_file() or not body_path.is_file():
            raise WorkspaceError(f"artifact_missing:{kind}")
        return (
            json.loads(meta_path.read_text(encoding="utf-8")),
            body_path.read_text(encoding="utf-8").rstrip("\n"),
        )

    def publish_approach_sources(self, sources: list[str]) -> None:
        shared = self.path / "shared"
        shared.mkdir(exist_ok=True)
        self._atomic_write(
            shared / "approach-sources.json",
            json.dumps({"sources": sources}, ensure_ascii=False, indent=2) + "\n",
        )

    def read_approach_sources(self) -> list[str]:
        path = self.path / "shared" / "approach-sources.json"
        if not path.is_file():
            return []
        value = json.loads(path.read_text(encoding="utf-8"))
        sources = value.get("sources", [])
        if not isinstance(sources, list) or any(not isinstance(x, str) or not x.strip() for x in sources):
            raise WorkspaceError("approach_source_file")
        return sources

    def publish_execution_outcome(self, kind: str, body: str, metadata: dict[str, Any] | None = None) -> None:
        output = self._turn_base() / "stages" / "50_execution" / "output"
        output.mkdir(parents=True, exist_ok=True)
        self._atomic_write(output / "current.md", body.rstrip() + "\n")
        payload = {"kind": kind}
        if metadata:
            payload.update(metadata)
        self._atomic_write(output / "current.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self.append_event("EXECUTION_OUTCOME_PUBLISHED", payload)

    def validate_confirmed_artifact(self, kind: str, artifact_id: str, body: str) -> None:
        meta, workspace_body = self.read_artifact(kind)
        if meta.get("artifact_id") != artifact_id or not meta.get("confirmed"):
            raise WorkspaceError(f"confirmed_artifact_binding:{kind}")
        if workspace_body != body:
            raise WorkspaceError(f"confirmed_artifact_modified:{kind}")

    def sync_unconfirmed_edit(self, kind: str, artifact_id: str, controller_body: str) -> str:
        output = self._artifact_stage(kind)
        meta, workspace_body = self.read_artifact(kind)
        if meta.get("artifact_id") != artifact_id:
            raise WorkspaceError(f"artifact_identity:{kind}")
        if meta.get("confirmed"):
            if workspace_body != controller_body:
                raise WorkspaceError(f"confirmed_artifact_modified:{kind}")
            return controller_body
        if workspace_body != controller_body:
            versions = output / "versions"
            versions.mkdir(parents=True, exist_ok=True)
            self._atomic_write(versions / f"{artifact_id}.md", workspace_body.rstrip() + "\n")
            meta["workspace_edited"] = True
            self._atomic_write(output / "current.json", json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
            self.append_event(
                "UNCONFIRMED_ARTIFACT_EDIT_DETECTED",
                {"kind": kind, "artifact_id": artifact_id},
            )
            return workspace_body
        return controller_body
