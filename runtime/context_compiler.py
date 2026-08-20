from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json

from runtime.standard_registry import StandardRegistry


_AUTO_SYMBOLS = {"OPERATION_ID", "APPLICABLE_STANDARD_CLAUSES", "HIGHER_PRIORITY_CONSTRAINTS"}


@dataclass(frozen=True)
class CompiledProjection:
    operation: str
    output_kind: str
    output_fields: tuple[str, ...]
    document: dict[str, Any]
    manifest: dict[str, Any]

    def render(self, bootstrap: str) -> str:
        return bootstrap.rstrip() + "\n\n" + json.dumps(self.document, ensure_ascii=False, indent=2) + "\n"


class ContextCompiler:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self.execution_contract = json.loads(
            (self.repo_root / "contracts" / "EXECUTION_CONTRACT.json").read_text(encoding="utf-8")
        )
        self.registry = StandardRegistry(self.repo_root)

    def compile(
        self,
        operation: str,
        values: dict[str, Any],
        *,
        higher_priority_constraints: Any = None,
    ) -> CompiledProjection:
        operations = self.execution_contract["operations"]
        if operation not in operations:
            raise ValueError(f"operation:{operation}")
        spec = operations[operation]
        include = tuple(spec["include"])
        expected = set(include) - _AUTO_SYMBOLS
        provided = set(values)
        missing = expected - provided
        extra = provided - expected
        if missing:
            raise ValueError(f"missing_symbols:{sorted(missing)}")
        if extra:
            raise ValueError(f"extra_symbols:{sorted(extra)}")

        clauses = self.registry.select(spec["requirements"])
        clause_values = [
            {"requirement_id": clause.requirement_id, "clause": clause.text}
            for clause in clauses
        ]
        ordered_inputs: dict[str, Any] = {}
        for symbol in include:
            if symbol == "OPERATION_ID":
                ordered_inputs[symbol] = operation
            elif symbol == "APPLICABLE_STANDARD_CLAUSES":
                ordered_inputs[symbol] = clause_values
            elif symbol == "HIGHER_PRIORITY_CONSTRAINTS":
                ordered_inputs[symbol] = higher_priority_constraints
            else:
                ordered_inputs[symbol] = values[symbol]

        schema_relative = spec.get("output_schema")
        if not isinstance(schema_relative, str):
            raise ValueError(f"output_schema:{operation}")
        schema_path = Path(schema_relative)
        if schema_path.is_absolute() or ".." in schema_path.parts:
            raise ValueError(f"output_schema_path:{operation}")
        full_schema_path = self.repo_root / schema_path
        if not full_schema_path.is_file():
            raise ValueError(f"output_schema_missing:{operation}")
        output_schema = json.loads(full_schema_path.read_text(encoding="utf-8"))

        document: dict[str, Any] = {
            "operation": operation,
            "output_kind": spec["output_kind"],
            "output_schema": output_schema,
            "operation_inputs": ordered_inputs,
        }
        if spec.get("artifact_kind"):
            document["artifact_kind"] = spec["artifact_kind"]

        clause_digests = {
            clause.requirement_id: sha256(clause.text.encode("utf-8")).hexdigest()
            for clause in clauses
        }
        manifest = {
            "operation": operation,
            "included_symbols": list(include),
            "excluded_symbols": list(spec.get("exclude", [])),
            "requirement_ids": list(spec["requirements"]),
            "clause_sha256": clause_digests,
            "output_kind": spec["output_kind"],
            "output_fields": list(spec.get("output_fields", [])),
            "output_schema": schema_relative,
            "output_schema_sha256": sha256(full_schema_path.read_bytes()).hexdigest(),
        }
        manifest["projection_sha256"] = sha256(
            json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return CompiledProjection(
            operation=operation,
            output_kind=spec["output_kind"],
            output_fields=tuple(spec.get("output_fields", [])),
            document=document,
            manifest=manifest,
        )
