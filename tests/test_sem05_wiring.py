"""Regression test for the SEM-05 wiring gap.

Prior to this patch, SEM-05 existed only as prose in
contracts/standards/SEMANTIC_INPUT_STANDARD.md: it was registered in neither
CONTRACT_MANIFEST.json's requirement_index nor EXECUTION_CONTRACT.json's
DRAFT_PROMPT/REVISE_PROMPT requirements, so ContextCompiler.compile() never
included it in APPLICABLE_STANDARD_CLAUSES and no worker ever saw it. This
test asserts the clause is actually present in the compiled projection for
both operations that produce Prompt Pseudocode, and that its text still
contains the load-bearing normative language if it is ever edited again.
"""
from __future__ import annotations

from pathlib import Path

from runtime.context_compiler import ContextCompiler

ROOT = Path(__file__).resolve().parents[1]


def _requirement_ids(document: dict) -> set[str]:
    clauses = document["operation_inputs"]["APPLICABLE_STANDARD_CLAUSES"]
    return {c["requirement_id"] for c in clauses}


def _clause_text(document: dict, requirement_id: str) -> str:
    clauses = document["operation_inputs"]["APPLICABLE_STANDARD_CLAUSES"]
    matches = [c["clause"] for c in clauses if c["requirement_id"] == requirement_id]
    assert len(matches) == 1, f"expected exactly one SEM-05 clause, got {len(matches)}"
    return matches[0]


def test_sem05_reaches_draft_prompt():
    compiler = ContextCompiler(ROOT)
    values = {
        "HOST_PROTOCOL_STATE": {"stage": "10_prompt", "has_prior_prompt": False},
        "SUBSTANTIVE_REQUEST": "hi",
    }
    projection = compiler.compile("DRAFT_PROMPT", values, higher_priority_constraints=None)
    assert "SEM-05" in _requirement_ids(projection.document)


def test_sem05_reaches_revise_prompt():
    compiler = ContextCompiler(ROOT)
    values = {
        "CURRENT_PROMPT_BODY": "Compare Kafka and RabbitMQ for event delivery.",
        "TASK_CHANGE_SOURCE": "This is not confirmed. The audience should be data engineers.",
    }
    projection = compiler.compile("REVISE_PROMPT", values, higher_priority_constraints=None)
    assert "SEM-05" in _requirement_ids(projection.document)


def test_revise_prompt_has_full_sem_family():
    # REVISE_PROMPT previously had zero SEM-* requirements at all (found
    # while wiring SEM-05 in); this asserts the whole family now reaches it.
    compiler = ContextCompiler(ROOT)
    values = {
        "CURRENT_PROMPT_BODY": "Compare Kafka and RabbitMQ for event delivery.",
        "TASK_CHANGE_SOURCE": "This is not confirmed. The audience should be data engineers.",
    }
    projection = compiler.compile("REVISE_PROMPT", values, higher_priority_constraints=None)
    ids = _requirement_ids(projection.document)
    assert {"SEM-01", "SEM-02", "SEM-03", "SEM-04", "SEM-05"} <= ids


def test_plan09_reaches_draft_plan_and_revise_plan():
    compiler = ContextCompiler(ROOT)
    common = {
        "CONFIRMED_PROMPT_BODY": "The user greets the assistant.",
        "CARRIED_APPROACH_SOURCES": None,
    }
    per_operation = {
        "DRAFT_PLAN": common,
        "REVISE_PLAN": {**common, "CURRENT_PLAN_BODY": "Reply with a greeting."},
    }
    for operation, values in per_operation.items():
        projection = compiler.compile(operation, values, higher_priority_constraints=None)
        assert "PLAN-09" in _requirement_ids(projection.document), operation
    compiler = ContextCompiler(ROOT)
    values = {
        "HOST_PROTOCOL_STATE": {"stage": "10_prompt", "has_prior_prompt": False},
        "SUBSTANTIVE_REQUEST": "hi",
    }
    projection = compiler.compile("DRAFT_PROMPT", values, higher_priority_constraints=None)
    text = _clause_text(projection.document, "SEM-05")
    # The clause must name the user as the required actor and must forbid
    # substituting the agent's anticipated response for the user's act.
    assert "MUST name the user as the actor" in text
    assert "MUST NOT substitute the agent's anticipated response" in text
