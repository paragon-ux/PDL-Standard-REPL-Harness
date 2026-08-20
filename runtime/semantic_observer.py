from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class ObservationSpec:
    check_id: str
    requirements: tuple[str, ...]
    resolver: str
    operations: tuple[str, ...]


class SemanticObserverRegistry:
    """Read-only registry for declared semantic checks.

    This module does not invoke a model, retry candidate work, mutate artifacts,
    or gate the baseline Condition C candidate path.
    """

    def __init__(self, repo_root: str | Path):
        root = Path(repo_root)
        contract = json.loads((root / "contracts" / "VERIFICATION_CONTRACT.json").read_text(encoding="utf-8"))
        self.mode = contract["baseline_profile"]["S"]
        self._checks = tuple(
            ObservationSpec(
                check_id=item["id"],
                requirements=tuple(item["requirements"]),
                resolver=item["resolver"],
                operations=tuple(item["operations"]),
            )
            for item in contract["checks"]
            if item["class"] == "S"
        )

    def for_operation(self, operation: str) -> tuple[ObservationSpec, ...]:
        return tuple(spec for spec in self._checks if operation in spec.operations)
