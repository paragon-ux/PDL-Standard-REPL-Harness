from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(payload)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_events(workspace: Any) -> list[dict[str, Any]]:
    if workspace is None:
        return []
    path = Path(workspace.path) / "events" / "events.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def controller_snapshot(engine: Any) -> dict[str, Any] | None:
    if engine is None or engine.controller is None:
        return None
    return {
        "controller_state": engine.controller.state.to_dict(),
        "workspace_id": engine.workspace.metadata.get("workspace_id") if engine.workspace is not None else None,
        "workspace_path": str(engine.workspace.path) if engine.workspace is not None else None,
    }


def event_delta(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    if len(after) >= len(before):
        new_events = after[len(before):]
    else:
        new_events = after
    return {
        "before_count": len(before),
        "after_count": len(after),
        "new": [
            {"at_utc": event.get("at_utc"), "kind": event.get("kind"), "payload": event.get("payload")}
            for event in new_events
        ],
    }
