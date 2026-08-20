from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class WorkerResult:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class TransportError(RuntimeError):
    """Worker/transport failure before PDL wire validity is evaluated."""


class WorkerAdapter(Protocol):
    def call(self, request: Any) -> WorkerResult:
        ...


def make_model_call(adapter: WorkerAdapter):
    def model_call(request: Any) -> str:
        return adapter.call(request).text

    return model_call
