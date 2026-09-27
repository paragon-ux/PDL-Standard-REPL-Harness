"""Unit tests for Sys1 Decision Recipes (Phase 2)."""

from __future__ import annotations

import pytest

from pdl_taskmaster.providers.sys1.recipes.activation_route import ActivationRouteRecipe
from pdl_taskmaster.providers.sys1.recipes.confirmation_match import ConfirmationMatchRecipe
from pdl_taskmaster.providers.sys1.recipes.review_facets import ReviewFacetsRecipe


def test_confirmation_match_agrees() -> None:
    recipe = ConfirmationMatchRecipe()
    req = recipe.build_request({"proposal": "Prompt Pseudocode...", "response": "confirm"})
    assert "confirmation" in req.questions
    assert "agrees" in req.questions["confirmation"].choices

    backend_response = {
        "answers": {
            "confirmation": {
                "choice": "agrees",
                "confidence": 0.98,
                "probabilities": {"agrees": 0.98, "rejects": 0.01, "unclear": 0.01},
            }
        }
    }
    result = recipe.parse_response(backend_response, duration_ms=12.5)
    assert result.status == "ready"
    assert result.verdict == "agrees"
    assert result.passed_gating is True

    wire = recipe.map_to_wire(result)
    assert wire["kind"] == "REVIEW_FACTS"
    assert wire["progression_requested"] is True
    assert wire["task_change_dimensions"] == []
    assert wire["approach_change_dimensions"] == []


def test_confirmation_match_rejects() -> None:
    recipe = ConfirmationMatchRecipe()
    backend_response = {
        "answers": {
            "confirmation": {
                "choice": "rejects",
                "confidence": 0.95,
                "probabilities": {"agrees": 0.02, "rejects": 0.95, "unclear": 0.03},
            }
        }
    }
    result = recipe.parse_response(backend_response, duration_ms=10.0)
    assert result.status == "ready"
    assert result.verdict == "rejects"
    wire = recipe.map_to_wire(result)
    assert wire["kind"] == "CANCEL"


def test_confirmation_match_unclear_falls_to_review() -> None:
    recipe = ConfirmationMatchRecipe()
    backend_response = {
        "answers": {
            "confirmation": {
                "choice": "unclear",
                "confidence": 0.92,
                "probabilities": {"agrees": 0.04, "rejects": 0.04, "unclear": 0.92},
            }
        }
    }
    result = recipe.parse_response(backend_response, duration_ms=10.0)
    assert result.status == "review"
    assert result.verdict == "unclear"


def test_review_facets_separates_task_and_approach() -> None:
    recipe = ReviewFacetsRecipe()
    req = recipe.build_request({
        "artifact_kind": "plan",
        "content": "Step 1... Step 2...",
        "feedback": "you have to plan your response now",
    })
    assert len(req.questions) == 4
    assert "revises_task" in req.questions
    assert "revises_approach" in req.questions

    # Simulate Sys1 classifying feedback about the plan as revises_approach=true, revises_task=false
    backend_response = {
        "answers": {
            "revises_task": {
                "choice": "false",
                "confidence": 0.95,
                "probabilities": {"true": 0.05, "false": 0.95},
            },
            "revises_approach": {
                "choice": "true",
                "confidence": 0.94,
                "probabilities": {"true": 0.94, "false": 0.06},
            },
            "requests_clarification": {
                "choice": "false",
                "confidence": 0.99,
                "probabilities": {"true": 0.01, "false": 0.99},
            },
            "is_acknowledgment": {
                "choice": "false",
                "confidence": 0.99,
                "probabilities": {"true": 0.01, "false": 0.99},
            },
        }
    }
    result = recipe.parse_response(backend_response, duration_ms=18.0)
    assert result.status == "ready"
    assert result.verdict == "revise_approach"
    assert result.labels["revises_task"] is False
    assert result.labels["revises_approach"] is True

    wire = recipe.map_to_wire(result)
    assert wire["kind"] == "REVIEW_FACTS"
    assert wire["task_change_dimensions"] == []
    assert wire["approach_change_dimensions"] == ["JUSTIFICATION_PROCEDURE"]
    assert wire["progression_requested"] is False


def test_activation_route_recipe() -> None:
    recipe = ActivationRouteRecipe()
    req = recipe.build_request({"request": "Partition the string racecar into palindromes."})
    assert "route" in req.questions

    backend_response = {
        "answers": {
            "route": {
                "choice": "APPLY_PROTOCOL",
                "confidence": 0.99,
                "probabilities": {"APPLY_PROTOCOL": 0.99, "PROTOCOL_DISCUSSION": 0.005, "BYPASS": 0.005},
            }
        }
    }
    result = recipe.parse_response(backend_response, duration_ms=15.0)
    assert result.status == "ready"
    assert result.verdict == "APPLY_PROTOCOL"

    wire = recipe.map_to_wire(result)
    assert wire["route"] == "APPLY_PROTOCOL"
    assert wire["response"] is None
