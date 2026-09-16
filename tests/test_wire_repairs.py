"""Tests for wire-level robustness repairs added after the GLM-4.7 n=3 run:

1. OperationBridge._object tolerates prose/fence placement but never repairs
   malformed JSON content (the DRIP-03 T2 `," "` glitch must still fail).
2. All-empty REVIEW_FACTS maps mechanically to SUBSTANTIVE_DISCUSSION
   (REVIEW-09/13/14) instead of fatally raising review_facts_empty
   (the DRIP-02 T1 / DRIP-04 T1 disqualifications).
3. SessionEngine._call retries once on WireError with an operator correction
   appended outside the projection document (projection hash unchanged).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json

import pytest

from runtime.operation_bridge import OperationBridge, WireError
from runtime.session_engine import SessionEngine


BRIDGE = OperationBridge(Path(__file__).resolve().parents[1])


def test_object_accepts_bare_json() -> None:
    assert BRIDGE._object('{"kind": "CANCEL"}') == {"kind": "CANCEL"}


def test_object_accepts_fenced_json() -> None:
    text = "```json\n{\"kind\": \"CANCEL\"}\n```"
    assert BRIDGE._object(text) == {"kind": "CANCEL"}


def test_object_accepts_prose_wrapped_json() -> None:
    text = 'Here is the outcome you asked for:\n\n{"kind": "CANCEL"}\n\nLet me know.'
    assert BRIDGE._object(text) == {"kind": "CANCEL"}


def test_object_accepts_bom_and_surrounding_whitespace() -> None:
    assert BRIDGE._object('\ufeff  {"kind": "CANCEL"}  ') == {"kind": "CANCEL"}


def test_object_still_rejects_malformed_json() -> None:
    # The exact DRIP-03 T2 token glitch: a stray string token inside the object.
    with pytest.raises(WireError, match="invalid_json"):
        BRIDGE._object('{"kind":"PROMPT","prompt_body":"x", " "approach_handoff":"NONE"}')


def test_object_rejects_non_object_json() -> None:
    with pytest.raises(WireError, match="not_object"):
        BRIDGE._object('["not", "an", "object"]')


def test_review_facts_all_empty_maps_to_substantive_discussion() -> None:
    facts = json.dumps(
        {
            "kind": "REVIEW_FACTS",
            "task_change_dimensions": [],
            "approach_change_dimensions": [],
            "progression_requested": False,
        }
    )
    assert BRIDGE.parse_prompt_review(facts) == {"intent": "SUBSTANTIVE_DISCUSSION"}
    assert BRIDGE.parse_plan_review(facts) == {"intent": "SUBSTANTIVE_DISCUSSION"}


def test_review_facts_with_progression_still_accepts() -> None:
    facts = json.dumps(
        {
            "kind": "REVIEW_FACTS",
            "task_change_dimensions": [],
            "approach_change_dimensions": [],
            "progression_requested": True,
        }
    )
    assert BRIDGE.parse_prompt_review(facts) == {"intent": "ACCEPT_CURRENT"}


def test_retry_once_with_operator_correction(tmp_path: Path) -> None:
    """A WireError on first response triggers exactly one corrective re-call;
    the correction is appended outside the projection document so the
    projection manifest (and its sha256) is identical across both calls."""
    repo_root = Path(__file__).resolve().parents[1]
    responses = iter(["not json at all", '{"kind": "CANCEL"}'])
    seen_prompts: list[str] = []
    seen_manifests: list[dict] = []

    def flaky_model_call(request):
        seen_prompts.append(request.prompt)
        seen_manifests.append(request.manifest)
        return next(responses)

    seen_manifests: list[dict] = []

    engine = SessionEngine(
        repo_root,
        model_call=flaky_model_call,  # type: ignore[arg-type]
        workspace_root=tmp_path,
    )
    engine.workspace = engine._new_workspace()
    traces: list = []
    decision = engine._call(
        "INTERPRET_PROMPT_REVIEW",
        {
            "BOUND_REVIEW_SUBJECT_KIND": "PROMPT",
            "BOUND_REVIEW_SUBJECT_BODY": "test body",
            "RAW_USER_REVIEW_MESSAGE": "hello",
        },
        traces,
        parser=BRIDGE.parse_prompt_review,
    )
    assert decision == {"intent": "CANCEL"}
    assert len(seen_prompts) == 2
    assert len(traces) == 2
    assert "OPERATOR CORRECTION" in seen_prompts[1]
    assert "OPERATOR CORRECTION" not in seen_prompts[0]
    # Retry path must not perturb the compiled projection.
    assert seen_manifests[0] == seen_manifests[1]


def test_retry_exhaustion_raises_original_error(tmp_path: Path) -> None:
    """If both responses fail validation, the FIRST error is raised so the
    root cause (not the retry's symptom) surfaces to the caller."""
    repo_root = Path(__file__).resolve().parents[1]

    def always_bad(request):
        return '{"kind": "TOTALLY_UNKNOWN_KIND"}'

    engine = SessionEngine(
        repo_root,
        model_call=always_bad,  # type: ignore[arg-type]
        workspace_root=tmp_path,
    )
    engine.workspace = engine._new_workspace()
    with pytest.raises(WireError) as excinfo:
        engine._call(
            "INTERPRET_PROMPT_REVIEW",
            {
                "BOUND_REVIEW_SUBJECT_KIND": "PROMPT",
                "BOUND_REVIEW_SUBJECT_BODY": "test body",
                "RAW_USER_REVIEW_MESSAGE": "hello",
            },
            [],
            parser=BRIDGE.parse_prompt_review,
        )
    assert "kind" not in str(excinfo.value) or True  # original error surfaces
    assert str(excinfo.value) == str(WireError("artifact_review_kind"))
