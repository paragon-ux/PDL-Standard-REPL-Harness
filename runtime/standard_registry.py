from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re


_DEFINITION = re.compile(r"^\*\*([A-Z]+-[0-9]{2})\s+—.*$", re.MULTILINE)


@dataclass(frozen=True)
class StandardClause:
    requirement_id: str
    text: str
    source: str


class StandardRegistry:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        manifest_path = self.repo_root / "contracts" / "CONTRACT_MANIFEST.json"
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.requirement_index: dict[str, str] = dict(self.manifest["requirement_index"])
        self._clauses = self._load()

    def _load(self) -> dict[str, StandardClause]:
        result: dict[str, StandardClause] = {}
        for requirement_id, relative in self.requirement_index.items():
            path = self.repo_root / relative
            text = path.read_text(encoding="utf-8")
            matches = [line for line in text.splitlines() if line.startswith(f"**{requirement_id} ")]
            if len(matches) != 1:
                raise ValueError(f"requirement_definition:{requirement_id}")
            if not _DEFINITION.match(matches[0]):
                raise ValueError(f"requirement_format:{requirement_id}")
            result[requirement_id] = StandardClause(requirement_id, matches[0], relative)
        if set(result) != set(self.requirement_index):
            raise ValueError("requirement_index")
        return result

    def get(self, requirement_id: str) -> StandardClause:
        return self._clauses[requirement_id]

    def select(self, requirement_ids: list[str] | tuple[str, ...]) -> tuple[StandardClause, ...]:
        return tuple(self.get(requirement_id) for requirement_id in requirement_ids)
