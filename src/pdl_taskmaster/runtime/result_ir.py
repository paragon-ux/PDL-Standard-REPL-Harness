"""Result Pseudocode decomposition IR (ADR-0009 prototype).

Structured result artifact emitted by the EXECUTE operation alongside the
native deliverable: the result is decomposed per file, reconciled against
the mechanically derived requirement IDs of the confirmed Prompt Pseudocode,
and grounded in execution-evidence citations that the controller validates
mechanically. Model-asserted content is never trusted:

  - every cited path MUST resolve inside the workspace;
  - every cited section marker MUST appear verbatim in the cited artifact;
  - every quoted observation MUST appear verbatim in the cited artifact;
  - every requirement ID derived from the confirmed prompt body MUST be
    reconciled exactly once.

Zero external dependencies (stdlib only), per the harness constraint.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# Commitment verbs: prompt-body lines opening with one of these are
# mechanically promoted to requirement IDs (R1..Rn, in order).
_COMMITMENT_VERB = re.compile(
    r"^(?:IMPLEMENT|DEFINE|GENERATE|DELIVER|ENSURE|PRESERVE|REMOVE|UPDATE|"
    r"MAINTAIN|FIX|SCAN|ALIGN|ELIMINATE|COMPARE|APPLY|MODIFY|LOCATE|CREATE|"
    r"VERIFY|REWRITE|REBUILD|PRESENT|ADD)\b"
)

_VALID_STATUS = {"satisfied", "partial", "open"}

RESULT_IR_INSTRUCTIONS_TEMPLATE = """The response MUST end with a fenced ```json block containing the Result IR object, exactly this shape:
{{"files": [{{"filename": "<name>.py", "satisfies": ["R<n>", ...], "evidence": {{"path": "<workspace-relative path of the artifact this file's content is grounded in>", "section": "<verbatim section marker inside that artifact, or omitted>"}}}}], "reconciliation": [{{"requirement": "R<n>", "status": "satisfied|partial|open", "evidence": {{"path": "...", "section": "...", "observed": "<verbatim quote from the cited artifact supporting this status>"}}}}, ...], "open_defects": [{{"id": "D<n>", "description": "<defect>", "evidence": {{"path": "...", "observed": "<verbatim quote>"}}}}]}}
Rules: cite ONLY the artifacts listed under AVAILABLE EVIDENCE PATHS below; every "observed" string MUST be copied verbatim from the cited artifact; every requirement ID MUST appear in "reconciliation" exactly once; do not invent paths, sections, quotes, or requirement IDs."""

_EVIDENCE_KEYS = ("path", "section", "observed")


def derive_requirements(prompt_body: str) -> list[str]:
    """Mechanically derive requirement IDs (R1..Rn) from the confirmed prompt."""
    reqs: list[str] = []
    for line in (prompt_body or "").splitlines():
        s = line.strip()
        if s and _COMMITMENT_VERB.match(s):
            reqs.append(s)
    return reqs


def render_instructions(
    requirements: list[str],
    repo_root: str | Path | None = None,
    evidence_paths: list[str] | None = None,
) -> str:
    numbered = "\n".join(f"R{i}: {r}" for i, r in enumerate(requirements, 1))
    paths = "\n".join(f"- {p}" for p in (evidence_paths or ["execution://body"]))
    return (
        "CONFIRMED REQUIREMENTS (mechanically derived; reconcile EVERY ID):\n"
        + (numbered or "R1: (no commitment lines detected)")
        + "\n\n"
        + load_standard_instructions(repo_root).replace(
            "{evidence_paths}", paths or "- execution://body"
        )
    )


def load_standard_instructions(repo_root: str | Path | None = None) -> str:
    """ADR-0009: the controller imports the Result IR standard at the EXECUTE
    stage and renders its instruction block verbatim. Single source of truth
    is contracts/standards/RESULT_STANDARD.md."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[3]
    standard = root / "contracts" / "standards" / "RESULT_STANDARD.md"
    text = standard.read_text(encoding="utf-8")
    m = re.search(
        r"<!-- RESULT-IR:INSTRUCTIONS.*?-->\s*\n(.*?)\n?<!-- /RESULT-IR:INSTRUCTIONS -->",
        text,
        re.S,
    )
    if not m:
        raise ValueError("result_standard_instructions_missing")
    return m.group(1).strip()


def extract_result_ir(body: str) -> dict | None:
    """Extract the Result IR from an execution body: the LAST fenced ```json
    block, or — as models sometimes emit it unfenced — a trailing raw JSON
    object starting with {\"files\"."""
    body = body or ""
    blocks = re.findall(r"```json\s*\n(.*?)```", body, re.S)
    for candidate in reversed(blocks):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    idx = body.rfind('{"files"')
    if idx >= 0:
        try:
            obj, _ = json.JSONDecoder().raw_decode(body[idx:])
        except json.JSONDecodeError:
            return None
        if isinstance(obj, dict):
            return obj
    return None


def _resolve_evidence(
    ev: object,
    workspace_path: Path,
    errors: list[str],
    where: str,
    execution_body: str | None = None,
) -> None:
    if not isinstance(ev, dict) or "path" not in ev:
        errors.append(f"{where}: evidence object with 'path' required")
        return
    raw = str(ev["path"]).replace("\\", "/")
    if raw == "execution://body":
        # Reserved self-reference (RS-04): resolves to the current execution
        # body — the just-produced deliverable, not yet on disk.
        if execution_body is None:
            errors.append(f"{where}: execution://body cited but no execution body available")
            return
        content = execution_body
    else:
        candidate = (workspace_path / raw).resolve()
        try:
            candidate.relative_to(workspace_path.resolve())
        except ValueError:
            errors.append(f"{where}: evidence path escapes workspace: {raw}")
            return
        if not candidate.is_file():
            errors.append(f"{where}: evidence path does not resolve: {raw}")
            return
        content = candidate.read_text(encoding="utf-8", errors="replace")
    section = ev.get("section")
    if section and str(section) not in content:
        errors.append(f"{where}: cited section marker not found in artifact: {section!r}")
    observed = ev.get("observed")
    if observed and str(observed).strip() not in content:
        errors.append(
            f"{where}: cited observation is not a verbatim substring of the artifact: {str(observed)[:80]!r}"
        )


def validate_result_ir(
    ir: object,
    workspace_path: str | Path,
    requirements: list[str],
    execution_body: str | None = None,
) -> tuple[list[str], dict]:
    """Mechanically validate a Result IR against the workspace filesystem.

    Returns (errors, normalized_ir). Empty errors means every structural,
    coverage, and evidence-citation constraint held.
    """
    errors: list[str] = []
    ws = Path(workspace_path).resolve()
    if not isinstance(ir, dict):
        return ["Result IR must be a JSON object"], {}

    files = ir.get("files")
    recon = ir.get("reconciliation")
    defects = ir.get("open_defects", [])
    if not isinstance(files, list) or not files:
        errors.append("'files' must be a non-empty array")
    if not isinstance(recon, list) or not recon:
        errors.append("'reconciliation' must be a non-empty array")
    if not isinstance(defects, list):
        errors.append("'open_defects' must be an array when present")

    # Requirement coverage: every derived ID reconciled exactly once.
    seen: dict[str, int] = {}
    if isinstance(recon, list):
        for i, entry in enumerate(recon, 1):
            if not isinstance(entry, dict):
                errors.append(f"reconciliation[{i}]: must be an object")
                continue
            rid = str(entry.get("requirement", "")).strip()
            seen[rid] = seen.get(rid, 0) + 1
            status = str(entry.get("status", "")).strip().lower()
            if status not in _VALID_STATUS:
                errors.append(f"reconciliation[{i}] ({rid}): invalid status {status!r}")
            if rid not in {f"R{j}" for j in range(1, len(requirements) + 1)}:
                errors.append(f"reconciliation[{i}]: unknown requirement ID {rid!r}")
            _resolve_evidence(entry.get("evidence"), ws, errors, f"reconciliation[{i}] ({rid})", execution_body)
    total = {f"R{j}" for j in range(1, len(requirements) + 1)}
    for rid in sorted(total - set(seen)):
        errors.append(f"requirement {rid} is not reconciled")
    for rid, n in sorted(seen.items()):
        if n > 1 and rid in total:
            errors.append(f"requirement {rid} reconciled {n} times (expected exactly once)")

    if isinstance(files, list):
        for i, f in enumerate(files, 1):
            if not isinstance(f, dict) or not str(f.get("filename", "")).strip():
                errors.append(f"files[{i}]: 'filename' required")
                continue
            _resolve_evidence(
                f.get("evidence"), ws, errors, f"files[{i}] ({f.get('filename')})", execution_body
            )

    if isinstance(defects, list):
        for i, d in enumerate(defects, 1):
            if not isinstance(d, dict) or not str(d.get("description", "")).strip():
                errors.append(f"open_defects[{i}]: 'description' required")
                continue
            _resolve_evidence(d.get("evidence"), ws, errors, f"open_defects[{i}]", execution_body)

    return errors, (ir if not errors else {})


def render_prior_ir_section(ir: object) -> str:
    """Render a validated prior Result IR for injection into the next epoch."""
    try:
        body = json.dumps(ir, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""
    return (
        "\n\n## PRIOR RESULT IR (mechanically validated by the host; "
        "reconciliation statuses and open defects are authoritative)\n"
        + body
    )


def render_execution_brief(ir: object | None, requirements: list[str]) -> str:
    """Host-side execution brief (ADR-0009 experiment): entity-dense steering
    assembled mechanically from the prior validated IR — open defects as the
    authoritative work list, delivery discipline to suppress cross-file churn.
    Mirrors the entity-extraction purpose of DRAFT_PROMPT at the execute
    boundary without an additional worker call."""
    lines = ["\n## EXECUTION BRIEF (host-assembled; authoritative)"]
    defects = (ir or {}).get("open_defects") or []
    open_reqs = [
        r for r in ((ir or {}).get("reconciliation") or [])
        if isinstance(r, dict) and r.get("status") in {"partial", "open"}
    ]
    if defects:
        lines.append("OPEN DEFECTS (fix these and only these):")
        for d in defects:
            lines.append(f"- {d.get('id')}: {d.get('description')}")
    elif open_reqs:
        lines.append("UNRESOLVED REQUIREMENTS:")
        for r in open_reqs:
            lines.append(f"- {r.get('requirement')}: {r.get('status')}")
    else:
        lines.append("NO OPEN DEFECTS recorded in the prior Result IR; if the task is a fix task, "
                     "the defect description is in the user message — fix exactly that.")
    lines.append(
        "DELIVERY DISCIPLINE: change only what the listed defects require; every file "
        "section MUST contain only code (no prose, no requirement echoes, no fence markers "
        "inside sections); reproduce all other files byte-identical; never weaken or "
        "hardcode tests to force a pass."
    )
    if requirements:
        lines.append("REQUIREMENT LEDGER: " + "; ".join(
            f"R{i}: {r.splitlines()[0][:80]}" for i, r in enumerate(requirements, 1)
        ))
    return "\n".join(lines)


def load_ir_from_deliverable(deliverable_text: str | None) -> dict | None:
    """Recover the embedded Result IR from a prior deliverable (restore/chaining)."""
    if not deliverable_text:
        return None
    ir = extract_result_ir(deliverable_text)
    return ir if isinstance(ir, dict) and ir.get("reconciliation") else None


def artifact_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _norm(text: str) -> str:
    """Whitespace-normalized form for verbatim entity matching (content, not
    layout, is the 4B check)."""
    return " ".join((text or "").split())


# ---------------------------------------------------------------------------
# Typed entity pipeline (ADR-0009 / TRD-0003 RS-02 extension): entities are
# parsed and classified at DRAFT_EXECUTE time; the host applies
# kind-appropriate mechanical checks instead of heuristic string filters.

_ENTITY_KINDS = {
    "delivery_marker": {"brief": "line", "deliverable": "line"},
    "api_signature": {"brief": "normalized", "deliverable": "normalized"},
    "constant": {"brief": "normalized", "deliverable": "normalized"},
    "wire_format": {"brief": "normalized", "deliverable": "normalized"},
    "threshold": {"brief": "normalized", "deliverable": "normalized"},
    "meta": {"brief": "normalized", "deliverable": None},
}


def parse_typed_entities(raw_entities: list) -> list[dict]:
    """Normalize raw entity entries (dicts per schema, or legacy plain strings)
    into typed records. Untyped strings become kind 'meta' (brief-only) so
    legacy emission degrades gracefully instead of triggering false retries."""
    typed = []
    for e in raw_entities or []:
        if isinstance(e, dict) and str(e.get("value", "")).strip():
            kind = str(e.get("kind", "meta")).strip()
            if kind not in _ENTITY_KINDS:
                kind = "meta"
            typed.append({
                "kind": kind,
                "value": str(e["value"]),
                "name": e.get("name"),
                "struct_format": e.get("struct_format"),
                "declared_size": e.get("declared_size"),
            })
        elif isinstance(e, str) and e.strip():
            typed.append({"kind": "meta", "value": e.strip(),
                          "name": None, "struct_format": None, "declared_size": None})
    return typed


def arithmetic_checks(typed_entities: list[dict]) -> list[str]:
    """Mechanical arithmetic validation over typed entities (host-side, stdlib).

    - wire_format: struct.calcsize(struct_format) MUST equal declared_size
      (catches native-alignment vs declared-size drift, e.g. HEADER_SIZE=16
      with a 20-byte '4s Q I' native layout).
    - constant with name MAGIC-like byte literal: the literal length MUST fit
      the wire_format's leading string-field width when both are declared
      (catches b'WAL01' truncated by a '4s' field).
    """
    import struct as _struct
    errors: list[str] = []
    wire = [e for e in typed_entities if e["kind"] == "wire_format"]
    for e in wire:
        fmt, declared = e.get("struct_format"), e.get("declared_size")
        if not fmt or declared is None:
            continue
        try:
            actual = _struct.calcsize(fmt)
        except struct.error as exc:
            errors.append(f"wire_format {fmt!r}: invalid struct format ({exc})")
            continue
        if actual != declared:
            errors.append(
                f"wire_format arithmetic mismatch: calcsize({fmt!r}) = {actual} "
                f"but declared_size = {declared}"
            )
    consts = [e for e in typed_entities if e["kind"] == "constant" and e.get("name")]
    wires = [e for e in typed_entities if e["kind"] == "wire_format" and e.get("struct_format")]
    for c in consts:
        val = c["value"]
        if not (val.startswith(("b'", 'b"')) and val.endswith(("'", '"'))):
            continue
        try:
            import ast as _ast
            literal = _ast.literal_eval(val)
        except (ValueError, SyntaxError):
            continue
        if not isinstance(literal, (bytes, bytearray)):
            continue
        for w in wires:
            m = re.search(r"(\d+)s", str(w["struct_format"]))
            if not m:
                continue
            width = int(m.group(1))
            if len(literal) > width:
                errors.append(
                    f"constant {c['name']} = {val} is {len(literal)} bytes but wire_format "
                    f"{w['struct_format']!r} allots a {width}-byte field (truncation on write)"
                )
    return errors


def entity_enforcement_misses(
    typed_entities: list[dict],
    brief_body: str,
    deliverable_body: str | None,
) -> tuple[list[str], list[str]]:
    """Apply per-kind enforcement. Returns (brief_misses, deliverable_misses)
    with kind-tagged strings. meta entities are never checked against the
    deliverable; delivery markers are checked line-verbatim."""
    brief_misses: list[str] = []
    deliv_misses: list[str] = []
    norm_brief, norm_deliv = _norm(brief_body), _norm(deliverable_body or "")
    deliv_lines = set((deliverable_body or "").splitlines())
    for e in typed_entities:
        kind, val = e["kind"], e["value"]
        rule = _ENTITY_KINDS[kind]
        if rule["brief"] == "line":
            if val not in brief_body:
                brief_misses.append(f"{kind}:{val}")
        elif _norm(val) not in norm_brief:
            brief_misses.append(f"{kind}:{val}")
        target = rule["deliverable"]
        if target is None:
            continue
        if target == "line":
            if val not in deliv_lines and val not in (deliverable_body or ""):
                deliv_misses.append(f"{kind}:{val}")
        elif _norm(val) not in norm_deliv:
            deliv_misses.append(f"{kind}:{val}")
    return brief_misses, deliv_misses
