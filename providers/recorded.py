from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import hashlib

from providers.base import WorkerResult


class ReplayMissError(RuntimeError):
    pass


class AmbiguousFixtureError(RuntimeError):
    pass


@dataclass
class RecordedEntry:
    response: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RecordedFixtureBuilder:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], list[RecordedEntry]] = {}
        self.order: list[tuple[str, str]] = []
        self.prompt_examples: dict[tuple[str, str], str] = {}

    def add(
        self,
        operation: str,
        prompt_sha256: str,
        response: str,
        metadata: dict[str, Any] | None = None,
        *,
        source: str = "fixture",
        prompt_text: str | None = None,
    ) -> None:
        key = (operation, prompt_sha256)
        self.entries.setdefault(key, []).append(
            RecordedEntry(response, {"source": source, **(metadata or {})})
        )
        if prompt_text is not None:
            self.prompt_examples.setdefault(key, prompt_text)
        if key not in self.order:
            self.order.append(key)

    def build(self, selected_fixture_id: str | None = None) -> "RecordedWorker":
        mapping: dict[tuple[str, str], RecordedEntry] = {}
        for key, entries in self.entries.items():
            unique = {entry.response: entry for entry in entries}
            if len(unique) == 1:
                mapping[key] = next(iter(unique.values()))
                continue
            if selected_fixture_id is None:
                raise AmbiguousFixtureError(
                    f"ambiguous replay mapping for {key[0]} prompt={key[1][:12]}; "
                    "provide an explicit fixture/run ID"
                )
            selected = [
                entry
                for entry in entries
                if entry.metadata.get("source") == selected_fixture_id
            ]
            if len(selected) != 1:
                raise AmbiguousFixtureError(
                    f"fixture ID {selected_fixture_id!r} does not resolve exactly one response "
                    f"for {key[0]} prompt={key[1][:12]}"
                )
            mapping[key] = selected[0]
        return RecordedWorker(mapping, list(self.order), dict(self.prompt_examples), dict(self.entries))


class RecordedWorker:
    """Deterministic replay worker.

    This is a qualification/test implementation of WorkerAdapter, not the
    general-purpose worker contract.
    """

    def __init__(
        self,
        mapping: dict[tuple[str, str], RecordedEntry],
        order: list[tuple[str, str]] | None = None,
        prompt_examples: dict[tuple[str, str], str] | None = None,
        entries: dict[tuple[str, str], list[RecordedEntry]] | None = None,
    ):
        self.mapping = mapping
        self.order = list(order or [])
        self.prompt_examples = prompt_examples or {}
        self.entries = entries or {}

    def call(self, request: Any) -> WorkerResult:
        key = (request.operation, hashlib.sha256(request.prompt.encode("utf-8")).hexdigest())
        entry = self.mapping.get(key)
        if entry is None:
            raise ReplayMissError(
                f"no recorded response for operation={request.operation} prompt_sha256={key[1][:12]}"
            )
        return WorkerResult(entry.response, dict(entry.metadata))

    def to_manifest(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for key, entry in self.mapping.items():
            operation, prompt_sha256 = key
            source = str(entry.metadata.get("source", "unknown"))
            fixture_id = hashlib.sha256(
                f"{source}|{operation}|{prompt_sha256}".encode("utf-8")
            ).hexdigest()[:16]
            rows.append(
                {
                    "source_evidence_run": source,
                    "operation": operation,
                    "prompt_sha256": prompt_sha256,
                    "raw_response_sha256": hashlib.sha256(entry.response.encode("utf-8")).hexdigest(),
                    "fixture_id": fixture_id,
                }
            )
        return rows
