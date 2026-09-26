"""Unit tests for TypeSafe Jev Decisions client & ADR-0012 Tripartite Confidence Gate."""

from __future__ import annotations

import pytest

from pdl_taskmaster.providers.jev_client import (
    CONFIDENCE_FLOOR,
    ENTROPY_CEIL,
    MARGIN_FLOOR,
    build_activation_question,
    build_review_question,
    evaluate_confidence_gate,
    map_activation_result,
    map_review_result,
)


def test_confidence_gate_high_confidence_passes():
    """A sharply peaked distribution with high confidence, wide margin, and low entropy passes."""
    answer = {
        "choice": "APPLY_PROTOCOL",
        "confidence": 0.95,
        "probabilities": {
            "APPLY_PROTOCOL": 0.95,
            "BYPASS": 0.03,
            "PROTOCOL_DISCUSSION": 0.01,
            "BLOCKED_BY_HIGHER_PRIORITY": 0.01,
        },
    }
    result = evaluate_confidence_gate(answer)
    assert result.passed is True
    assert result.choice == "APPLY_PROTOCOL"
    assert result.confidence == 0.95
    assert result.margin >= MARGIN_FLOOR
    assert result.entropy <= ENTROPY_CEIL


def test_confidence_gate_low_confidence_fails():
    """Confidence below 0.85 fails the gate."""
    answer = {
        "choice": "BYPASS",
        "confidence": 0.75,
        "probabilities": {
            "BYPASS": 0.75,
            "APPLY_PROTOCOL": 0.20,
            "PROTOCOL_DISCUSSION": 0.05,
        },
    }
    result = evaluate_confidence_gate(answer)
    assert result.passed is False
    assert result.confidence < CONFIDENCE_FLOOR


def test_confidence_gate_narrow_margin_fails():
    """Narrow margin between top-2 choices fails the gate even if confidence is relatively high."""
    answer = {
        "choice": "APPLY_PROTOCOL",
        "confidence": 0.86,
        "probabilities": {
            "APPLY_PROTOCOL": 0.86,
            "BYPASS": 0.84,  # margin is 0.02 < 0.40
        },
    }
    result = evaluate_confidence_gate(answer)
    assert result.passed is False
    assert result.margin < MARGIN_FLOOR


def test_map_activation_result_fail_closed():
    """Gate failure on activation fails closed to APPLY_PROTOCOL."""
    low_conf_body = {
        "answers": {
            "route": {
                "choice": "BYPASS",
                "confidence": 0.60,
                "probabilities": {"BYPASS": 0.60, "APPLY_PROTOCOL": 0.40},
            }
        }
    }
    mapped = map_activation_result(low_conf_body)
    assert mapped["route"] == "APPLY_PROTOCOL"
    assert mapped["confidence"] <= 0.50


def test_map_activation_result_high_confidence():
    """Gate pass on activation routes cleanly."""
    high_conf_body = {
        "answers": {
            "route": {
                "choice": "BYPASS",
                "confidence": 0.98,
                "probabilities": {"BYPASS": 0.98, "APPLY_PROTOCOL": 0.02},
            }
        }
    }
    mapped = map_activation_result(high_conf_body)
    assert mapped["route"] == "BYPASS"
    assert mapped["confidence"] == 0.98


def test_map_review_result_confirmation():
    """Confirmation passes review and requests progression."""
    body = {
        "answers": {
            "progression_requested": {
                "choice": "YES",
                "confidence": 0.99,
                "probabilities": {"YES": 0.99, "NO": 0.01},
            },
            "revises_task": {
                "choice": "NO",
                "confidence": 0.99,
                "probabilities": {"NO": 0.99, "YES": 0.01},
            },
        }
    }
    mapped = map_review_result(body)
    assert mapped["kind"] == "REVIEW_FACTS"
    assert mapped["progression_requested"] is True
    assert mapped["task_change_dimensions"] == []
    assert mapped["confidence"] == 0.99


def test_map_review_result_revision():
    """Revision requests substantive change."""
    body = {
        "answers": {
            "progression_requested": {
                "choice": "NO",
                "confidence": 0.96,
                "probabilities": {"NO": 0.96, "YES": 0.04},
            },
            "revises_task": {
                "choice": "YES",
                "confidence": 0.97,
                "probabilities": {"YES": 0.97, "NO": 0.03},
            },
        }
    }
    mapped = map_review_result(body)
    assert mapped["kind"] == "REVIEW_FACTS"
    assert mapped["progression_requested"] is False
    assert mapped["task_change_dimensions"] == ["ACTION_SUBJECT_OR_OBJECT"]


def test_map_review_result_fail_closed_unresolved():
    """Ambiguous feedback trips the gate and falls back to UNRESOLVED (REVIEW-09 Human Card)."""
    body = {
        "answers": {
            "progression_requested": {
                "choice": "YES",
                "confidence": 0.60,
                "probabilities": {"YES": 0.60, "NO": 0.40},
            },
            "revises_task": {
                "choice": "NO",
                "confidence": 0.55,
                "probabilities": {"NO": 0.55, "YES": 0.45},
            },
        }
    }
    mapped = map_review_result(body)
    assert mapped["kind"] == "UNRESOLVED"
    assert mapped["confidence"] <= 0.50


def test_api_worker_try_jev_decisions_success(monkeypatch, tmp_path):
    """ApiWorker successfully delegates to Jev and returns valid WorkerResult."""
    from pdl_taskmaster.providers.api_worker import ApiWorker
    from pdl_taskmaster.providers.base import WorkerResult
    import pdl_taskmaster.providers.jev_client as jc_module

    fake_resp = {
        "answers": {
            "route": {
                "choice": "APPLY_PROTOCOL",
                "confidence": 0.95,
                "probabilities": {"APPLY_PROTOCOL": 0.95, "BYPASS": 0.05},
            }
        },
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }

    monkeypatch.setattr(
        jc_module,
        "call_jev_decisions",
        lambda **kwargs: (fake_resp, 0.042),
    )

    monkeypatch.setenv("TEST_KEY_ENV", "dummy_key")

    worker = ApiWorker(
        model="openai/gpt-oss-120b",
        repo_root=tmp_path,
        api_key_env="TEST_KEY_ENV",
        use_jev=True,
    )

    class FakeProjection:
        document = {"operation_inputs": {"RAW_USER_MESSAGE": "Test message"}}

    class FakeRequest:
        operation = "INTERPRET_ACTIVATION"
        prompt = "test prompt"
        projection = FakeProjection()

    res = worker._try_jev_decisions(FakeRequest(), "INTERPRET_ACTIVATION")
    assert isinstance(res, WorkerResult)
    assert res.metadata["worker"] == "jev"
    assert res.metadata["latency_ms"] == 42.0
    assert '"route": "APPLY_PROTOCOL"' in res.text

