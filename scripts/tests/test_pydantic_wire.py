from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest
from pydantic import ValidationError

from scripts.runtime.operation_bridge import OperationBridge, WireError
from scripts.runtime.session_engine import SessionEngine
from scripts.runtime.wire_payloads import (
    OPERATION_PAYLOAD_MODELS,
    ActivationDecisionPayload,
    ActivationRoute,
    BootstrapAnalysisPayload,
    PromptDraftPayload,
    ReviewFactsData,
    format_validation_feedback,
    get_operation_pydantic_schema,
)

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = OperationBridge(ROOT)


def test_all_operations_have_valid_pydantic_json_schema() -> None:
    expected_ops = {
        "INTERPRET_ACTIVATION",
        "BOOTSTRAP_ANALYSIS",
        "DRAFT_PROMPT",
        "DRAFT_PLAN",
        "REVISE_PROMPT",
        "REVISE_PLAN",
        "INTERPRET_PROMPT_REVIEW",
        "INTERPRET_PLAN_REVIEW",
        "INTERPRET_EXECUTION_INPUT",
        "ANSWER_PROTOCOL_DISCUSSION",
        "DRAFT_EXECUTION",
        "EMIT_RESULT_IR",
        "EXECUTE",
    }
    for op in expected_ops:
        schema = get_operation_pydantic_schema(op)
        assert isinstance(schema, dict), f"Operation {op} missing Pydantic JSON schema"
        assert "type" in schema or "anyOf" in schema or "$defs" in schema


def test_activation_payload_enforces_route_and_response() -> None:
    # Valid APPLY_PROTOCOL without response
    res = BRIDGE.parse_activation('{"route": "APPLY_PROTOCOL"}')
    assert res.route == ActivationRoute.APPLY_PROTOCOL
    assert res.response is None

    # Extra response on APPLY_PROTOCOL forbidden
    with pytest.raises(WireError, match="extra_fields"):
        BRIDGE.parse_activation('{"route": "APPLY_PROTOCOL", "response": "should not be here"}')

    # BLOCKED_BY_HIGHER_PRIORITY requires response
    blocked = BRIDGE.parse_activation('{"route": "BLOCKED_BY_HIGHER_PRIORITY", "response": "Policy violation"}')
    assert blocked.route == ActivationRoute.BLOCKED_BY_HIGHER_PRIORITY
    assert blocked.response == "Policy violation"

    with pytest.raises(WireError, match="blocked_response"):
        BRIDGE.parse_activation('{"route": "BLOCKED_BY_HIGHER_PRIORITY", "response": ""}')


def test_prompt_draft_discriminated_union() -> None:
    # Valid prompt with default approach_handoff and entities
    draft = BRIDGE.parse_prompt_draft('{"kind": "PROMPT", "prompt_body": "Analyze data"}')
    assert draft.kind == "PROMPT"
    assert draft.prompt_body == "Analyze data"
    assert draft.approach_handoff == "NONE"
    assert draft.task_entities == ()

    # Invalid approach handoff
    with pytest.raises(WireError, match="approach_handoff"):
        BRIDGE.parse_prompt_draft('{"kind": "PROMPT", "prompt_body": "Analyze data", "approach_handoff": "INVALID"}')

    # Empty prompt body
    with pytest.raises(WireError, match="prompt_body"):
        BRIDGE.parse_prompt_draft('{"kind": "PROMPT", "prompt_body": "  "}')

    # Blocked draft
    blocked = BRIDGE.parse_prompt_draft(
        '{"kind": "TASK_BLOCKED_BY_HIGHER_PRIORITY", "blocking_basis": "PROVIDER_PLATFORM_SAFETY_PRIVACY_PERMISSION_OR_TOOL", "response": "blocked"}'
    )
    assert blocked.kind == "TASK_BLOCKED_BY_HIGHER_PRIORITY"
    assert blocked.response == "blocked"


def test_review_facts_dimension_deduplication() -> None:
    # Duplicate dimensions rejected
    with pytest.raises(WireError, match="task_change_dimensions"):
        BRIDGE.parse_prompt_review(
            json.dumps({
                "kind": "REVIEW_FACTS",
                "task_change_dimensions": ["ACTION_SUBJECT_OR_OBJECT", "ACTION_SUBJECT_OR_OBJECT"],
                "approach_change_dimensions": [],
                "progression_requested": False,
            })
        )


def test_precision_operator_correction_in_session_engine(tmp_path: Path) -> None:
    seen_prompts: list[str] = []

    def flaky_model(request):
        seen_prompts.append(request.prompt)
        if len(seen_prompts) == 1:
            # Drop required field 'task_entities'
            return json.dumps({
                "kind": "ANALYSIS",
                "task_summary": "Do work",
                "approach_notes": "None",
                "risk_notes": "None",
            })
        # Conforming retry
        return json.dumps({
            "kind": "ANALYSIS",
            "task_summary": "Do work",
            "approach_notes": "None",
            "risk_notes": "None",
            "task_entities": ["work"],
        })

    engine = SessionEngine(ROOT, model_call=flaky_model, workspace_root=tmp_path)
    engine.workspace = engine._new_workspace()
    traces: list = []
    res = engine._call(
        "BOOTSTRAP_ANALYSIS",
        {
            "HOST_PROTOCOL_STATE": "BOOTSTRAP_ANALYSIS",
            "RAW_UNTRUSTED_CONTENT": "Do work",
        },
        traces,
        parser=BRIDGE.parse_bootstrap_analysis,
    )
    assert res["task_entities"] == ["work"]
    assert len(seen_prompts) == 2
    retry_prompt = seen_prompts[1]
    assert "OPERATOR CORRECTION: Validation failed on field 'task_entities': Field required" in retry_prompt
    assert "Emit exactly one conforming JSON object matching the declared schema." in retry_prompt


def test_system1_fail_closed_confidence_gate() -> None:
    # High confidence System 1 review classification proceeds
    high_conf = json.dumps({
        "kind": "REVIEW_FACTS",
        "task_change_dimensions": [],
        "approach_change_dimensions": [],
        "progression_requested": True,
        "confidence": 0.95,
    })
    res_high = BRIDGE.parse_prompt_review(high_conf)
    assert res_high["intent"] == "ACCEPT_CURRENT"

    # Low confidence (< 0.85) System 1 review fails closed to UNRESOLVED per ADR-0012 / REVIEW-09
    low_conf = json.dumps({
        "kind": "REVIEW_FACTS",
        "task_change_dimensions": [],
        "approach_change_dimensions": [],
        "progression_requested": True,
        "confidence": 0.65,
    })
    res_low = BRIDGE.parse_prompt_review(low_conf)
    assert res_low["intent"] == "UNRESOLVED"

    # Low confidence (< 0.85) System 1 activation classification fails closed to APPLY_PROTOCOL
    low_act = json.dumps({
        "route": "BYPASS",
        "confidence": 0.60,
    })
    act_res = BRIDGE.parse_activation(low_act)
    assert act_res.route == ActivationRoute.APPLY_PROTOCOL
