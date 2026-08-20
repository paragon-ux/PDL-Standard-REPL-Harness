from __future__ import annotations

import json

from providers.base import WorkerResult


class LiveStubWorker:
    """Deterministic non-recorded worker for live-capability tests.

    Label: DEVELOPMENT / LIVE DEMONSTRATION WORKER
    NOT A QUALIFIED R2S MEASUREMENT CONDITION.

    This adapter does not reference case IDs, evidence files, or recorded
    turn sequences. It is intentionally generic so observation can be tested
    against arbitrary new sessions.
    """

    def call(self, request) -> WorkerResult:
        operation = request.operation
        if operation == "INTERPRET_ACTIVATION":
            payload = {"route": "APPLY_PROTOCOL"}
        elif operation == "DRAFT_PROMPT":
            payload = {
                "kind": "PROMPT",
                "prompt_body": "EXPLAIN the user's requested topic in plain terms.",
                "approach_handoff": "NONE",
            }
        elif operation in {"INTERPRET_PROMPT_REVIEW", "INTERPRET_PLAN_REVIEW"}:
            payload = {
                "kind": "REVIEW_FACTS",
                "task_change_dimensions": [],
                "approach_change_dimensions": [],
                "progression_requested": True,
            }
        elif operation == "DRAFT_PLAN":
            payload = {
                "neutral_plan_body": "1. Define the topic.\n2. Explain the key mechanisms.\n3. Summarize practical implications."
            }
        elif operation == "EXECUTE":
            payload = {"kind": "RESULT", "body": "Completed."}
        else:
            raise RuntimeError(f"unhandled live stub operation: {operation}")
        return WorkerResult(json.dumps(payload, ensure_ascii=False), {"worker": "live-stub", "mode": "live-demonstration"})
