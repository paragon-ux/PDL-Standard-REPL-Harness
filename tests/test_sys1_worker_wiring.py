from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from pdl_taskmaster.providers.api_worker import ApiWorker
from pdl_taskmaster.providers.base import WorkerResult


class DummyInvocation:
    stage = "10_prompt"
    invocation_id = "inv_001"


class DummyProjection:
    def __init__(self, operation: str, op_inputs: dict):
        self.document = {
            "operation": operation,
            "operation_inputs": op_inputs,
        }


class DummyRequest:
    def __init__(self, operation: str, op_inputs: dict, prompt: str = ""):
        self.operation = operation
        self.projection = DummyProjection(operation, op_inputs)
        self.workspace_invocation = DummyInvocation()
        self.manifest = {"output_kind": "json_object"}
        self.prompt = prompt or json.dumps(self.projection.document)


def test_api_worker_activation_sys1_delegation(tmp_path: Path) -> None:
    worker = ApiWorker(repo_root=tmp_path)
    worker.sys1_client = MagicMock()
    worker.sys1_client.is_configured = True
    worker.sys1_client.model = "typesafe/sys1-latest"
    worker.sys1_client.call.return_value = (
        {
            "answers": {
                "route": {
                    "choice": "APPLY_PROTOCOL",
                    "confidence": 0.99,
                    "probabilities": {"APPLY_PROTOCOL": 0.99, "BYPASS": 0.01},
                }
            }
        },
        12.0,
    )

    req = DummyRequest("INTERPRET_ACTIVATION", {"RAW_USER_MESSAGE": "Solve this riddle"})
    result = worker.call(req)
    assert isinstance(result, WorkerResult)
    data = json.loads(result.text)
    assert data["route"] == "APPLY_PROTOCOL"
    assert result.metadata["worker"] == "sys1"
    assert result.metadata["recipe"] == "activation-route"


def test_api_worker_prompt_review_agrees_sys1_delegation(tmp_path: Path) -> None:
    worker = ApiWorker(repo_root=tmp_path)
    worker.sys1_client = MagicMock()
    worker.sys1_client.is_configured = True
    worker.sys1_client.model = "typesafe/sys1-latest"
    worker.sys1_client.call.return_value = (
        {
            "answers": {
                "confirmation": {
                    "choice": "agrees",
                    "confidence": 0.98,
                    "probabilities": {"agrees": 0.98, "rejects": 0.01, "unclear": 0.01},
                }
            }
        },
        10.0,
    )

    req = DummyRequest(
        "INTERPRET_PROMPT_REVIEW",
        {
            "BOUND_REVIEW_SUBJECT_BODY": "IDENTIFY something",
            "RAW_USER_REVIEW_MESSAGE": "looks good to me, proceed",
        },
    )
    result = worker.call(req)
    assert isinstance(result, WorkerResult)
    data = json.loads(result.text)
    assert data["kind"] == "REVIEW_FACTS"
    assert data["progression_requested"] is True
    assert result.metadata["worker"] == "sys1"
    assert result.metadata["recipe"] == "confirmation-match"


def test_api_worker_prompt_review_facets_sys1_delegation(tmp_path: Path) -> None:
    worker = ApiWorker(repo_root=tmp_path)
    worker.sys1_client = MagicMock()
    worker.sys1_client.is_configured = True
    worker.sys1_client.model = "typesafe/sys1-latest"
    # First call to confirmation_match returns unclear
    # Second call to review_facets returns revise_approach
    worker.sys1_client.call.side_effect = [
        (
            {
                "answers": {
                    "confirmation": {
                        "choice": "unclear",
                        "confidence": 0.90,
                        "probabilities": {"agrees": 0.05, "rejects": 0.05, "unclear": 0.90},
                    }
                }
            },
            8.0,
        ),
        (
            {
                "answers": {
                    "revises_task": {"choice": "false", "confidence": 0.95},
                    "revises_approach": {"choice": "true", "confidence": 0.94},
                    "requests_clarification": {"choice": "false", "confidence": 0.99},
                    "is_acknowledgment": {"choice": "false", "confidence": 0.99},
                }
            },
            15.0,
        ),
    ]

    req = DummyRequest(
        "INTERPRET_PLAN_REVIEW",
        {
            "BOUND_REVIEW_SUBJECT_BODY": "IDENTIFY something",
            "RAW_USER_REVIEW_MESSAGE": "explain the algorithm steps in more detail",
        },
    )
    result = worker.call(req)
    assert isinstance(result, WorkerResult)
    data = json.loads(result.text)
    assert data["kind"] == "REVIEW_FACTS"
    assert data["approach_change_dimensions"] == ["JUSTIFICATION_PROCEDURE"]
    assert result.metadata["worker"] == "sys1"
    assert result.metadata["recipe"] == "review-facets"


def test_api_worker_fallback_when_sys1_unconfigured(tmp_path: Path) -> None:
    worker = ApiWorker(repo_root=tmp_path)
    worker.sys1_client = MagicMock()
    worker.sys1_client.is_configured = False
    with patch.object(
        worker,
        "_send_json_with_retries",
        return_value={
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"route": "APPLY_PROTOCOL"}'}],
                }
            ]
        },
    ):
        with patch.object(worker, "_resolve_api_key", return_value="dummy_key"):
            req = DummyRequest("INTERPRET_ACTIVATION", {"RAW_USER_MESSAGE": "test"})
            result = worker.call(req)
            assert result.metadata["worker"] == "api"


def test_session_engine_sys1_problem_classification(tmp_path: Path) -> None:
    from pdl_taskmaster.runtime.session_engine import SessionEngine

    mock_sys1 = MagicMock()
    mock_sys1.is_configured = True
    mock_sys1.call.return_value = (
        {
            "answers": {
                "problem_class": {
                    "choice": "VERIFIED_EXECUTION",
                    "confidence": 0.96,
                    "probabilities": {"VERIFIED_EXECUTION": 0.96, "STANDARD_EXECUTION": 0.04},
                }
            }
        },
        14.0,
    )

    def dummy_model(req: Any) -> str:
        op = req.operation
        if op == "INTERPRET_ACTIVATION":
            return json.dumps({"route": "APPLY_PROTOCOL", "response": None})
        if op == "BOOTSTRAP_ANALYSIS":
            return json.dumps({
                "kind": "ANALYSIS",
                "task_summary": "Task summary",
                "approach_notes": "",
                "risk_notes": "",
                "task_entities": [],
            })
        if op == "DRAFT_PROMPT":
            return json.dumps({
                "kind": "PROMPT",
                "prompt_body": "FIND valid assignment",
                "approach_handoff": "NONE",
                "task_entities": [],
            })
        return "{}"

    root = Path(__file__).resolve().parents[1]
    engine = SessionEngine(
        root,
        model_call=dummy_model,
        workspace_root=tmp_path,
        sys1_client=mock_sys1,
    )
    # Use request text that does NOT match deterministic regex, e.g. "Find valid assignment"
    engine.handle_user_message("Find valid assignment")
    assert engine._requires_verified_execution is True
    assert mock_sys1.call.called

