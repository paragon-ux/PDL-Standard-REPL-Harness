from __future__ import annotations

import json
import pytest

from pdl_taskmaster.runtime.result_ir import load_ir_from_deliverable
from pdl_taskmaster.runtime.session_engine import SessionEngine


def test_load_ir_with_witness():
    deliverable = """
YES, the set of 6 integers can be partitioned into 2 sum triples.

```json
{
  "files": [
    {
      "filename": "result.txt",
      "satisfies": ["R1"],
      "evidence": {"path": "execution://body"}
    }
  ],
  "reconciliation": [
    {
      "requirement": "R1",
      "status": "satisfied",
      "evidence": {"path": "execution://body"}
    }
  ],
  "open_defects": [],
  "witness": {
    "polarity": "positive",
    "evidence": {"path": "execution://witness"},
    "data": {
      "triples": [[1, 2, 3], [4, 5, 9]]
    }
  }
}
```
"""
    ir = load_ir_from_deliverable(deliverable)
    assert ir is not None
    assert "witness" in ir
    assert ir["witness"]["polarity"] == "positive"
    assert ir["witness"]["data"]["triples"] == [[1, 2, 3], [4, 5, 9]]


def test_witness_projection_with_retained_witness(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "contracts" / "standards").mkdir(parents=True)
    (repo_root / "contracts" / "standards" / "RESULT_STANDARD.md").write_text(
        "<!-- RESULT-IR:INSTRUCTIONS -->\nResult IR template\n<!-- /RESULT-IR:INSTRUCTIONS -->",
        encoding="utf-8",
    )

    engine = SessionEngine(
        str(repo_root),
        lambda req: '{"kind": "RESULT", "body": "Explaining the work..."}',
        workspace_root=tmp_path / "workspaces",
    )

    # Deliverable with witness
    deliverable = """
YES
```json
{
  "files": [{"filename": "out.txt", "satisfies": ["R1"], "evidence": {"path": "execution://body"}}],
  "reconciliation": [{"requirement": "R1", "status": "satisfied", "evidence": {"path": "execution://body"}}],
  "open_defects": [],
  "witness": {
    "polarity": "positive",
    "evidence": {"path": "execution://witness"},
    "data": {"triples": [[1, 2, 3]]}
  }
}
```
"""
    block = engine.build_introspection_projection(deliverable)
    assert "PRIOR TURN WITNESS RECORD (PROJECTED GROUND TRUTH)" in block
    assert '"triples"' in block
    assert "1" in block and "2" in block and "3" in block
    assert "Cite ONLY the verified data" in block


def test_witness_projection_without_retained_witness(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "contracts" / "standards").mkdir(parents=True)
    (repo_root / "contracts" / "standards" / "RESULT_STANDARD.md").write_text(
        "<!-- RESULT-IR:INSTRUCTIONS -->\nResult IR template\n<!-- /RESULT-IR:INSTRUCTIONS -->",
        encoding="utf-8",
    )

    engine = SessionEngine(
        str(repo_root),
        lambda req: '{"kind": "RESULT", "body": "No trace..."}',
        workspace_root=tmp_path / "workspaces",
    )

    # Deliverable without witness (Session 9 turn 1 scenario)
    deliverable_no_witness = """
YES
```json
{
  "files": [{"filename": "out.txt", "satisfies": ["R1"], "evidence": {"path": "execution://body"}}],
  "reconciliation": [{"requirement": "R1", "status": "satisfied", "evidence": {"path": "execution://body"}}],
  "open_defects": []
}
```
"""
    block = engine.build_introspection_projection(deliverable_no_witness)
    assert "PRIOR TURN WITNESS RECORD (PROJECTED GROUND TRUTH)" in block
    assert "NO WITNESS RECORD RETAINED FOR PRIOR TURN" in block
    assert "You MUST state plainly that no trace or witness was retained" in block
    assert "Do NOT fabricate, invent, or reconstruct" in block


def test_parse_sandbox_witness_and_body_projection():
    from pdl_taskmaster.runtime.session_engine import _parse_sandbox_witness
    from pdl_taskmaster.verification.output_verifier import OutputVerifier

    # 1. Test json stdout parsing
    out1 = '{"triples": [[1, 2, 3], [4, 5, 9]]}'
    cand1 = _parse_sandbox_witness(out1)
    assert cand1 is not None
    assert cand1["polarity"] == "positive"
    assert cand1["data"]["triples"] == [[1, 2, 3], [4, 5, 9]]

    # 2. Test python tuple list stdout parsing
    out2 = '[(1, 2, 3), (4, 5, 9), (6, 7, 13)]'
    cand2 = _parse_sandbox_witness(out2)
    assert cand2 is not None
    assert cand2["polarity"] == "positive"
    assert cand2["data"]["triples"] == [[1, 2, 3], [4, 5, 9], [6, 7, 13]]

    # 3. Test labeled path/solution stdout parsing (e.g. Hamiltonian path)
    out3 = "Hamiltonian path found: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]"
    cand3 = _parse_sandbox_witness(out3)
    assert cand3 is not None
    assert cand3["polarity"] == "positive"
    assert cand3["data"]["solution"] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

    # 4. Test structured negative search stdout parsing
    out4 = 'WITNESS = {"polarity": "negative", "search_exhausted": true, "nodes_explored": 42, "method": "dfs"}'
    cand4 = _parse_sandbox_witness(out4)
    assert cand4 is not None
    assert cand4["polarity"] == "negative"
    assert cand4["search_exhausted"] is True
    assert cand4["nodes_explored"] == 42

    # 5. Test that missing witness fails closed without regex-scraping body text (ADR-0018 / GUARD-03)
    verifier = OutputVerifier()
    body_with_triples = "The solution triples are (1, 2, 3), (4, 5, 9), and (6, 7, 13)."
    verdict = verifier.check(
        None,
        {"prompt_body": "PARTITION list into sum triples", "supplied_input": "1, 2, 3, 4, 5, 9, 6, 7, 13"},
        body=body_with_triples,
    )
    assert verdict.valid is False
    assert "Missing witness in Result IR" in (verdict.diagnostic or "")


