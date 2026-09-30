"""Anti-Overfitting and Benchmark Integrity Guardrail Unit Tests (GUARD-01 to GUARD-05).

Verifies that the PDL-Taskmaster harness maintains absolute neutrality and does not
harbor benchmark-gaming heuristics, prompt-targeted token hacks, or synthetic solver injections.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_guard01_no_synthetic_carried_approach_injection():
    """GUARD-01: session_engine._draft_plan must NOT inject synthetic carried approaches."""
    session_engine_file = ROOT / "src" / "pdl_taskmaster" / "runtime" / "session_engine.py"
    text = session_engine_file.read_text(encoding="utf-8")

    # Locate _draft_plan definition
    assert "def _draft_plan(" in text
    draft_plan_body = text.split("def _draft_plan(")[1].split("def ")[0]

    # Must NOT inject synthetic carried approach strings
    prohibited_snippets = [
        "search for the partition triples",
        "Algorithm X",
        "DLX",
        "backtracking solver script",
        "subset sum solver script",
    ]
    for snippet in prohibited_snippets:
        assert snippet not in draft_plan_body, (
            f"GUARD-01 VIOLATION: Found synthetic solver injection '{snippet}' in _draft_plan."
        )


def test_guard02_problem_class_clean_patterns():
    """GUARD-02: problem_class must not target conversational, riddle, or family logic keywords."""
    problem_class_file = ROOT / "src" / "pdl_taskmaster" / "providers" / "sys1" / "recipes" / "problem_class.py"
    text = problem_class_file.read_text(encoding="utf-8")

    # Combinatorial regex patterns must not include conversational logic/riddle tokens
    prohibited_tokens = [
        "sisters?",
        "brothers?",
        "how\\s+many\\s+sisters",
        "family\\s+relationship",
        "riddle",
    ]
    for token in prohibited_tokens:
        assert token not in text, (
            f"GUARD-02 VIOLATION: Found benchmark-targeted token '{token}' in problem_class.py."
        )


def test_guard02_activation_route_no_hardcoded_refusal_literals():
    """GUARD-02: activation_route refusal strings must not hardcode benchmark entities."""
    activation_route_file = ROOT / "src" / "pdl_taskmaster" / "providers" / "sys1" / "recipes" / "activation_route.py"
    text = activation_route_file.read_text(encoding="utf-8")

    # Refusal string must dynamically format matched package name rather than hardcoding ('frostbitedb')
    assert "('frostbitedb')" not in text, (
        "GUARD-02 VIOLATION: Found hardcoded refusal entity ('frostbitedb') in activation_route.py."
    )


def test_guard03_output_verifier_triples_not_standalone():
    """GUARD-03: output_verifier must not match standalone 'triples' without partition context."""
    output_verifier_file = ROOT / "src" / "pdl_taskmaster" / "verification" / "output_verifier.py"
    text = output_verifier_file.read_text(encoding="utf-8")

    # Must not contain unconditioned '"triples" in text_lower'
    assert 'if "triples" in text_lower or' not in text, (
        "GUARD-03 VIOLATION: Found unconditioned 'triples' containment check in output_verifier.py."
    )


def test_guard05_contract_manifest_sha256_synchronized():
    """GUARD-05: CONTRACT_MANIFEST.json must have 0 SHA-256 hash divergences."""
    manifest_file = ROOT / "contracts" / "CONTRACT_MANIFEST.json"
    assert manifest_file.is_file()

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    mismatches = []
    for entry in manifest.get("files", []):
        file_path = ROOT / entry["path"]
        assert file_path.is_file(), f"Manifest references missing file: {entry['path']}"
        raw_bytes = file_path.read_bytes()
        if file_path.suffix in {".md", ".json", ".txt", ".py", ".yaml", ".yml"}:
            raw_bytes = raw_bytes.replace(b"\r\n", b"\n")
        actual_sha = hashlib.sha256(raw_bytes).hexdigest()
        if entry["sha256"] != actual_sha:
            mismatches.append(f"{entry['path']}: expected {entry['sha256'][:10]} got {actual_sha[:10]}")

    assert not mismatches, f"CONTRACT_MANIFEST.json hash divergences found:\n" + "\n".join(mismatches)


def test_plan_soundness_accepts_pure_deduction_plan():
    """GUARD-03: Plan soundness must accept pure analytical/deductive plans without code."""
    from pdl_taskmaster.verification.plan_soundness import validate_plan_soundness

    analytical_plan = (
        "ANALYZE the sibling relationships for Alice and her family\n"
        "DEDUCE the total number of female siblings including Alice\n"
        "COMPUTE the number of sisters that each brother has\n"
        "EMIT the result in terms of M"
    )
    # For standard execution tasks, plan must be 100% valid
    result = validate_plan_soundness(analytical_plan, requires_verified_execution=False)
    assert result.valid
    assert len(result.violations) == 0


def test_guard_no_mrv_or_algorithmic_coaching_in_harness():
    """GUARD-04: Harness prompts and runtime must NOT spoon-feed MRV or specific algorithms."""
    targets = [
        ROOT / "src" / "pdl_taskmaster" / "runtime" / "session_engine.py",
        ROOT / "src" / "pdl_taskmaster" / "runtime" / "result_ir.py",
        ROOT / "src" / "pdl_taskmaster" / "providers" / "api_worker.py",
        ROOT / "src" / "pdl_taskmaster" / "verification" / "plan_soundness.py",
        ROOT / "src" / "pdl_taskmaster" / "verification" / "sandbox.py",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\bMRV\b", text, re.I), (
            f"GUARD-04 VIOLATION: Found algorithmic coaching 'MRV' in {path.name}"
        )
        assert "Alice has M sisters" not in text, (
            f"GUARD-04 VIOLATION: Found prompt-specific answer in {path.name}"
        )


def test_guard_no_witness_fabrication_or_regex_scraping():
    """GUARD-03: Verifiers must NOT regex-scrape deliverable text or invent fake exploration numbers."""
    checker_file = ROOT / "src" / "pdl_taskmaster" / "verification" / "checkers" / "partition_sum_triples.py"
    checker_text = checker_file.read_text(encoding="utf-8")
    assert "_extract_triples_from_text" not in checker_text, (
        "GUARD-03 VIOLATION: Found text regex scraping in partition_sum_triples.py"
    )

    session_engine_file = ROOT / "src" / "pdl_taskmaster" / "runtime" / "session_engine.py"
    se_text = session_engine_file.read_text(encoding="utf-8")
    assert '"nodes_explored": 100' not in se_text, (
        "GUARD-03 VIOLATION: Found fabricated negative witness numbers in session_engine.py"
    )


def test_guard_no_benchmark_probe_interceptions():
    """GUARD-02: System 1 must NOT hardcode benchmark trap packages."""
    route_file = ROOT / "src" / "pdl_taskmaster" / "providers" / "sys1" / "recipes" / "activation_route.py"
    route_text = route_file.read_text(encoding="utf-8")
    assert "frostbite" not in route_text.lower(), (
        "GUARD-02 VIOLATION: Found hardcoded benchmark probe package 'frostbite' in activation_route.py"
    )


def test_benchmark_contamination_scan():
    """GUARD-01/02/04: Source code must have ZERO benchmark prompt IDs or probe tokens."""
    src_dir = ROOT / "src" / "pdl_taskmaster"
    prompt_id_pattern = re.compile(r"\b(0[1-9]|1[0-5])-(0[1-7])\b")
    prohibited_tokens = [
        "frostbite",
        "frostbitedb",
        "schur_triples",
        "exact_cover_dlx",
        "alice has m sisters",
    ]

    violations: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        prompt_match = prompt_id_pattern.search(content)
        if prompt_match:
            violations.append(
                f"{py_file.relative_to(ROOT)}: Contains benchmark prompt ID '{prompt_match.group(0)}'"
            )
        lower_content = content.lower()
        for token in prohibited_tokens:
            if token in lower_content:
                violations.append(
                    f"{py_file.relative_to(ROOT)}: Contains benchmark probe token '{token}'"
                )

    assert not violations, (
        "GUARD VIOLATION: Benchmark contamination found in production source:\n"
        + "\n".join(violations)
    )


