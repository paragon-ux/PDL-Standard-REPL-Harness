from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import shutil
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
        self.execution_contract = json.loads(
            (self.repo_root / "contracts" / "EXECUTION_CONTRACT.json").read_text(encoding="utf-8")
        )

    @classmethod
    def create(cls, repo_root: str | Path, workspace_root: str | Path) -> "WorkspaceRun":
        repo_root = Path(repo_root)
        workspace_root = Path(workspace_root)
        workspace_root.mkdir(parents=True, exist_ok=True)
        workspace_id = f"W-{uuid.uuid4().hex[:12]}"
        path = workspace_root / workspace_id
        if path.exists():
            raise WorkspaceError("workspace_collision")
        template = repo_root / "workspace-template"
        if not template.is_dir():
            raise WorkspaceError("workspace_template_missing")
        shutil.copytree(template, path)
        (path / "state").mkdir(exist_ok=True)
        (path / "events").mkdir(exist_ok=True)
        metadata = {
            "schema_version": cls.SCHEMA,
            "workspace_id": workspace_id,
            "protocol_instance_id": None,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "icm_reference": "arXiv:2603.16021v2",
            "context_flow": "filesystem_stage_handoffs",
            "control_flow": "mechanical_controller",
        }
        cls._atomic_write(path / "workspace.json", json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        run = cls(repo_root, path)
        run.append_event("WORKSPACE_CREATED", {"workspace_id": workspace_id})
        return run

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
        events = self.path / "events" / "events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        with events.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @property
    def controller_state_path(self) -> Path:
        return self.path / "state" / "controller-state.json"

    @property
    def protocol_instance_id(self) -> str | None:
        value = self.metadata.get("protocol_instance_id")
        return value if isinstance(value, str) else None

    def bind_protocol(self, instance_id: str) -> None:
        current = self.protocol_instance_id
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
        if not isinstance(stage, str) or not stage:
            raise WorkspaceError(f"workspace_stage:{operation}")
        if not (self.path / "stages" / stage).is_dir():
            raise WorkspaceError(f"workspace_stage_missing:{stage}")
        return stage

    def _next_invocation_id(self, stage: str, operation: str) -> str:
        counter_path = self.path / "state" / "invocation-counter.json"
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
        stage_path = self.path / "stages" / stage
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
            return self.path / "stages" / "10_prompt" / "output"
        if kind == "plan":
            return self.path / "stages" / "30_plan" / "output"
        raise WorkspaceError(f"artifact_kind:{kind}")

    def publish_artifact(self, kind: str, artifact_id: str, body: str, *, confirmed: bool, source_prompt_id: str | None = None) -> None:
        output = self._artifact_stage(kind)
        versions = output / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        self._atomic_write(versions / f"{artifact_id}.md", body.rstrip() + "\n")
        self._atomic_write(output / "current.md", body.rstrip() + "\n")
        self._atomic_write(
            output / "current.json",
            json.dumps(
                {
                    "artifact_id": artifact_id,
                    "confirmed": confirmed,
                    "source_prompt_id": source_prompt_id,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
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
        output = self.path / "stages" / "50_execution" / "output"
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
