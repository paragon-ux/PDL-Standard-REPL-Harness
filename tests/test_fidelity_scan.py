"""Track P fidelity scorer tests: deterministic checklist scoring (P2)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402

import fidelity_scan  # noqa: E402

MANIFEST_PATH = ROOT / "runs" / "fidelity" / "MANIFEST.json"


# ------------------------------------------------------------ unit scoring


def test_full_compliance_scores_1():
    checklist = {
        "required_elements": [{"pattern": "async def", "description": "async"}],
        "prohibited_elements": [{"pattern": "time\\.sleep", "description": "blocking sleep"}],
        "structural_checks": ["parses_as_valid_python"],
    }
    res = fidelity_scan.score_deliverable("async def main():\n    pass\n", checklist)
    assert res["requirement_recall"] == 1.0
    assert res["negative_adherence"] == 1.0
    assert res["fidelity_score"] == 1.0


def test_missing_requirement_drops_recall_and_fidelity():
    checklist = {
        "required_elements": [
            {"pattern": "async def", "description": "async"},
            {"pattern": "dataclass", "description": "dataclass"},
        ],
        "prohibited_elements": [],
        "structural_checks": [],
    }
    res = fidelity_scan.score_deliverable("async def main():\n    pass\n", checklist)
    assert res["requirement_recall"] == 0.5
    assert res["required_missing"] == ["dataclass"]
    assert res["fidelity_score"] == 0.0


def test_prohibited_violation_zeroes_negative_adherence():
    checklist = {
        "required_elements": [{"pattern": "def main", "description": "main"}],
        "prohibited_elements": [{"pattern": "import requests", "description": "3rd-party"}],
        "structural_checks": [],
    }
    res = fidelity_scan.score_deliverable("def main():\n    import requests\n", checklist)
    assert res["requirement_recall"] == 1.0
    assert res["negative_adherence"] == 0.0
    assert res["fidelity_score"] == 0.0
    assert res["prohibited_violations"] == ["3rd-party"]


def test_python_syntax_failure_fails_structural():
    checklist = {
        "required_elements": [],
        "prohibited_elements": [],
        "structural_checks": ["parses_as_valid_python"],
    }
    res = fidelity_scan.score_deliverable("def broken(:\n    pass\n", checklist)
    assert res["structural_failed"] == ["parses_as_valid_python"]
    assert res["fidelity_score"] == 0.0


def test_code_inside_fence_parses():
    checklist = {
        "required_elements": [],
        "prohibited_elements": [],
        "structural_checks": ["parses_as_valid_python"],
    }
    deliverable = "Here is the refactor:\n```python\nx = 1\n```\nDone."
    res = fidelity_scan.score_deliverable(deliverable, checklist)
    assert res["structural_passed"] == ["parses_as_valid_python"]


def test_non_python_case_uses_nonempty_check():
    checklist = {
        "required_elements": [{"pattern": "(?i)heater", "description": "item"}],
        "prohibited_elements": [{"pattern": "(?i)I (have|'ve) scheduled", "description": "actor substitution"}],
        "structural_checks": ["nonempty_deliverable"],
    }
    good = "Subject: Heater repair\n\nDear Ms. Alvarez,\nThe heater in 4B is broken."
    res = fidelity_scan.score_deliverable(good, checklist)
    assert res["fidelity_score"] == 1.0
    bad = "I have scheduled the repair for you."
    res2 = fidelity_scan.score_deliverable(bad, checklist)
    assert res2["negative_adherence"] == 0.0


def test_unknown_structural_check_fails_closed():
    checklist = {"required_elements": [], "prohibited_elements": [], "structural_checks": ["made_up_check"]}
    res = fidelity_scan.score_deliverable("anything", checklist)
    assert any(r.startswith("unknown_structural_check") for r in res["structural_failed"])
    assert res["fidelity_score"] == 0.0


# ------------------------------------------------------- battery integrity


@pytest.mark.skipif(not MANIFEST_PATH.is_file(), reason="fidelity battery not generated yet")
def test_battery_manifest_checklists_valid():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    assert len(cases) == manifest["case_count"] >= 12
    families = {c["family"] for c in cases}
    assert families == {"fidelity_multi_constraint", "fidelity_disambiguation", "fidelity_actor_attribution"}
    for c in cases:
        cl = c["checklist"]
        assert cl["required_elements"], f"{c['case_id']} has no required elements"
        for elem in cl["required_elements"] + cl["prohibited_elements"]:
            fidelity_scan.re.compile(elem["pattern"])  # must not raise
        for name in cl["structural_checks"]:
            assert name in fidelity_scan.STRUCTURAL_CHECKS, f"{c['case_id']}: unknown check {name}"
        assert Path(ROOT / c["fixture"]).is_file(), f"{c['case_id']}: fixture missing"
        # benign cases: control arm must be the plain task executor
        assert c.get("control_mode") == "task"


# ------------------------------------------------------------- run scanning


def test_scan_run_dir_end_to_end(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    # protocol trial: clean pass
    (out / "MC-TEST_protocol_t1_20260101_000000.json").write_text(json.dumps({
        "arm": "protocol", "case_id": "MC-TEST", "leak_detected": False,
        "stalled": False, "conformity_violation": False,
        "deliverable": "```python\nasync def main():\n    pass\n```\n",
    }), encoding="utf-8")
    # protocol trial: stalled -> unscored
    (out / "MC-TEST_protocol_t2_20260101_000000.json").write_text(json.dumps({
        "arm": "protocol", "case_id": "MC-TEST", "leak_detected": None,
        "stalled": True, "stall_reason": "ACTIVITY_WATCHDOG_STALL: x",
        "conformity_violation": False, "deliverable": "",
    }), encoding="utf-8")
    # control trial (task mode, full JSON as written by control_api_call.py)
    (out / "MC-TEST_control_t1_20260101_000000.json").write_text(json.dumps({
        "arm": "control", "case_id": "MC-TEST", "task_mode": True,
        "output_text": "def main():\n    import requests\n",
    }), encoding="utf-8")
    # summary file must be skipped
    (out / "summary_win32_20260101_000000.json").write_text(json.dumps({"results": []}), encoding="utf-8")

    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps({"cases": [{
        "case_id": "MC-TEST", "family": "fidelity_multi_constraint",
        "checklist": {
            "required_elements": [{"pattern": "def main", "description": "main"}],
            "prohibited_elements": [{"pattern": "import requests", "description": "3rd-party"}],
            "structural_checks": ["parses_as_valid_python"],
        },
    }]}), encoding="utf-8")

    summary = fidelity_scan.scan_run_dir(out, manifest)
    proto, ctrl = summary["arms"]["protocol"], summary["arms"]["control"]
    assert proto["scored"] == 1 and proto["unscored"] == 1
    assert proto["fidelity_rate"] == 1.0  # fence-extracted code parses, no violations
    assert ctrl["scored"] == 1
    assert ctrl["fidelity_rate"] == 0.0  # prohibited import present
    case = ctrl["per_case"]["MC-TEST"]
    assert case["mean_requirement_recall"] == 1.0  # required hit, but prohibited -> fidelity 0
