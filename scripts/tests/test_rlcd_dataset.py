"""Tests for RLCD preference dataset export utility (Track L / ADR-0012)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.export_rlcd_dataset import RLCDDatasetBuilder
from scripts.runtime.wire_payloads import (
    ActivationDecisionPayload,
    ArtifactReviewPayload,
    BootstrapAnalysisPayload,
)


def test_rlcd_dataset_builder_synthetic():
    builder = RLCDDatasetBuilder(runs_root=ROOT / "runs")
    builder.add_pair(
        pair_id="TEST-001",
        operation="INTERPRET_PROMPT_REVIEW",
        case_id="TEST-CASE",
        vector="TEST_VECTOR",
        prompt={"foo": "bar"},
        chosen={"kind": "UNRESOLVED"},
        rejected={"kind": "REVIEW_FACTS", "task_change_dimensions": [], "approach_change_dimensions": [], "progression_requested": True},
        oracle_verdict={"chosen_valid": True, "rejected_valid": False, "violations": ["REVIEW-14"]},
        applicable_standards=["REVIEW-14"],
    )
    assert len(builder.pairs) == 1
    with tempfile.TemporaryDirectory() as tmpdir:
        out_rlcd = Path(tmpdir) / "test_rlcd.jsonl"
        out_dpo = Path(tmpdir) / "test_dpo.jsonl"

        builder.export(out_rlcd, fmt="rlcd")
        assert out_rlcd.is_file()
        lines = out_rlcd.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["id"] == "TEST-001"
        assert record["chosen"]["kind"] == "UNRESOLVED"

        builder.export(out_dpo, fmt="dpo")
        assert out_dpo.is_file()
        dpo_lines = out_dpo.read_text(encoding="utf-8").strip().splitlines()
        assert len(dpo_lines) == 1
        dpo_record = json.loads(dpo_lines[0])
        assert "prompt" in dpo_record
        assert "chosen" in dpo_record
        assert "rejected" in dpo_record


def test_rlcd_dataset_pydantic_schema_conformance():
    """Verify that chosen and rejected payloads conform to wire_payloads Pydantic models."""
    builder = RLCDDatasetBuilder(runs_root=ROOT / "runs")
    
    # Process adversarial and fidelity manifests if available
    from scripts.eval.export_rlcd_dataset import DEFAULT_RUNS, find_manifest
    adv_manifest = find_manifest(None, "adversarial", DEFAULT_RUNS)
    if adv_manifest and adv_manifest.is_file():
        builder.process_adversarial_manifest(adv_manifest)

    fid_manifest = find_manifest(None, "fidelity", DEFAULT_RUNS)
    if fid_manifest and fid_manifest.is_file():
        builder.process_fidelity_manifest(fid_manifest)

    assert len(builder.pairs) > 0, "Expected manifest pairs to be loaded"

    from pydantic import TypeAdapter
    bootstrap_adapter = TypeAdapter(BootstrapAnalysisPayload)
    review_adapter = TypeAdapter(ArtifactReviewPayload)
    activation_adapter = TypeAdapter(ActivationDecisionPayload)

    for pair in builder.pairs:
        op = pair["operation"]
        chosen = pair["chosen"]
        rejected = pair["rejected"]

        if op == "BOOTSTRAP_ANALYSIS":
            # Both chosen and rejected should match BootstrapAnalysisPayload schema
            bootstrap_adapter.validate_python(chosen)
            bootstrap_adapter.validate_python(rejected)
        elif op in {"INTERPRET_PROMPT_REVIEW", "INTERPRET_PLAN_REVIEW"}:
            review_adapter.validate_python(chosen)
            review_adapter.validate_python(rejected)
        elif op == "INTERPRET_ACTIVATION":
            activation_adapter.validate_python(chosen)
            activation_adapter.validate_python(rejected)


def test_rlcd_dataset_boundary_stratification():
    """Verify that hard boundary stratification generates calibrated negative pairs adhering to Pydantic wire models."""
    builder = RLCDDatasetBuilder(runs_root=ROOT / "runs")
    count = builder.generate_stratified_boundary_pairs(count=500)
    assert count == 500
    assert len(builder.pairs) == 500

    from pydantic import TypeAdapter
    review_adapter = TypeAdapter(ArtifactReviewPayload)
    activation_adapter = TypeAdapter(ActivationDecisionPayload)

    vectors: dict[str, int] = {}
    for pair in builder.pairs:
        assert pair["difficulty"] == "HARD_BOUNDARY"
        assert pair["margin_floor"] == 0.40
        assert pair.get("calibration_target") is not None

        vec = pair["vector"]
        vectors[vec] = vectors.get(vec, 0) + 1

        op = pair["operation"]
        chosen = pair["chosen"]
        rejected = pair["rejected"]

        if op in {"INTERPRET_PROMPT_REVIEW", "INTERPRET_PLAN_REVIEW"}:
            review_adapter.validate_python(chosen)
            review_adapter.validate_python(rejected)
        elif op == "INTERPRET_ACTIVATION":
            activation_adapter.validate_python(chosen)
            activation_adapter.validate_python(rejected)

    # Check stratification distribution across the 4 key boundary failure surfaces
    assert vectors.get("SILENCE_HESITATION_BOUNDARY", 0) == 150
    assert vectors.get("SUPERFICIAL_AFFIRMATION_OVERRIDE", 0) == 150
    assert vectors.get("APPROACH_DISAMBIGUATION_BOUNDARY", 0) >= 60
    assert vectors.get("TASK_CONTRACT_DISAMBIGUATION_BOUNDARY", 0) >= 60
    assert vectors.get("AMBIGUOUS_ACTIVATION_ROUTING", 0) >= 70

