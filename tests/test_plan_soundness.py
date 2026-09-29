from __future__ import annotations

import pytest

from pdl_taskmaster.providers.sys1.recipes.problem_class import ProblemClassRecipe
from pdl_taskmaster.verification.plan_soundness import (
    PlanSoundnessResult,
    validate_plan_soundness,
)


def test_problem_class_recipe_classification():
    recipe = ProblemClassRecipe()
    assert recipe.name == "problem-class"

    # Deterministic check for combinatorial existence / witness problems
    assert recipe.classify_text_deterministic("Determine if there exists a partition into 15 Schur triples")
    assert recipe.classify_text_deterministic("Can this set be partitioned into sum triples?")
    assert recipe.classify_text_deterministic("Solve minimal cut palindrome partitioning for the string")
    assert recipe.classify_text_deterministic("Find whether a 3-coloring of this graph exists")
    assert not recipe.classify_text_deterministic("Write a Python function to parse JSON files")
    assert not recipe.classify_text_deterministic("Hello, how are you today?")

    # sys1 build_request test
    req = recipe.build_request({"request": "Find 15 disjoint sum triples"})
    assert "problem_class" in req.questions
    assert "VERIFIED_EXECUTION" in req.questions["problem_class"].choices


def test_plan_soundness_deferral_rejected():
    # Test deferred plan text
    deferred_plan = (
        "1. Read the list of 45 integers.\n"
        "2. The partitioning algorithm is deferred to execution stage.\n"
        "3. Deliver the output."
    )
    result = validate_plan_soundness(deferred_plan, requires_verified_execution=True)
    assert not result.valid
    assert any("deferral marker" in v for v in result.violations)

    tbd_plan = (
        "1. Scan inputs.\n"
        "2. Solving method is TBD.\n"
        "3. Output result."
    )
    result_tbd = validate_plan_soundness(tbd_plan, requires_verified_execution=True)
    assert not result_tbd.valid
    assert any("deferral marker" in v for v in result_tbd.violations)


def test_plan_soundness_undisclosed_greedy_rejected():
    # Test undisclosed greedy / no-backtrack scan proposed as decisive
    greedy_plan = (
        "1. Parse the 45 integers into an ascending list.\n"
        "2. Run a single greedy pass without backtracking to select triples satisfying a + b = c.\n"
        "3. If any element cannot be paired, conclude NO.\n"
        "4. Print the final answer."
    )
    result = validate_plan_soundness(greedy_plan, requires_verified_execution=True)
    assert not result.valid
    assert any("incomplete heuristic" in v for v in result.violations)


def test_plan_soundness_disclosed_heuristic_accepted():
    # Test greedy scan with explicit disclosure that failure does not prove non-existence
    disclosed_plan = (
        "1. Parse integers.\n"
        "2. Execute a Python script implementing a greedy search heuristic.\n"
        "3. Note that heuristic failure does not prove non-existence; if no partition is found, label result unverified.\n"
        "4. Return the result."
    )
    result = validate_plan_soundness(disclosed_plan, requires_verified_execution=True)
    assert result.valid
    assert len(result.violations) == 0


def test_plan_soundness_complete_search_accepted():
    # Test concrete code execution with complete backtracking search
    sound_plan = (
        "1. Parse the 45 candidate integers from the input.\n"
        "2. Execute a Python solver script implementing backtracking search with MRV heuristic to find 15 disjoint triples where a + b = c.\n"
        "3. If a valid partition is found, emit YES with the witness triples.\n"
        "4. If search space is exhausted without a solution, emit NO with search_exhausted certificate."
    )
    result = validate_plan_soundness(sound_plan, requires_verified_execution=True)
    assert result.valid
    assert len(result.violations) == 0


def test_plan_soundness_missing_execution_commitment():
    # Plan that has no code execution commitment
    vague_plan = (
        "1. Ponder the mathematical properties of the numbers.\n"
        "2. Introspect the relationships between values.\n"
        "3. Conclude whether a partition exists."
    )
    result = validate_plan_soundness(vague_plan, requires_verified_execution=True)
    assert not result.valid
    assert any("commit to concrete code execution" in v for v in result.violations)


def test_plan_soundness_bypassed_for_standard_tasks():
    # Standard task does not require combinatorial soundness
    standard_plan = "1. Greet the user.\n2. Explain what PDL is."
    result = validate_plan_soundness(standard_plan, requires_verified_execution=False)
    assert result.valid
    assert len(result.violations) == 0


def test_plan_soundness_combinatorial_mrv_required():
    # Naive search without MRV heuristic for partition problem is rejected
    naive_partition_plan = (
        "1. EXECUTE a Python backtracking solver script to search for a partition of the integers into triples satisfying a + b = c.\n"
        "2. If found, emit YES with triples.\n"
        "3. Else, emit NO."
    )
    res_naive = validate_plan_soundness(naive_partition_plan, requires_verified_execution=True)
    assert not res_naive.valid
    assert any("Minimum Remaining Values (MRV)" in v for v in res_naive.violations)

    # Adding MRV heuristic passes
    mrv_partition_plan = (
        "1. EXECUTE a Python backtracking solver script with Minimum Remaining Values (MRV) heuristic to search for a partition of the integers into triples satisfying a + b = c.\n"
        "2. If found, emit YES with triples.\n"
        "3. Else, emit NO."
    )
    res_mrv = validate_plan_soundness(mrv_partition_plan, requires_verified_execution=True)
    assert res_mrv.valid
    assert len(res_mrv.violations) == 0

