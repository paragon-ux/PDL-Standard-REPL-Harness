from __future__ import annotations

from pathlib import Path
from typing import Any
import json


class JsonlSink:
    def __init__(self, output_dir: str | Path, session_id: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.output_dir / f"{session_id}.jsonl"
        self._handle = self.path.open("a", encoding="utf-8", newline="\n")

    def record(self, record: dict[str, Any]) -> None:
        self._handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()
