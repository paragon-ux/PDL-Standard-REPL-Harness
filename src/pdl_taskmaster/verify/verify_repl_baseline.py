from __future__ import annotations

"""One deterministic verification entry point for the standalone REPL harness.

Checks: required runtime/instructional files, import integrity, fixture
integrity, external-source-repo leakage, fresh-workspace lifecycle, result
delivery, and resume. All workspaces are created in temporary directories.
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


_SRC = "PDL-Standard-R2S"
SOURCE_REPO_MARKERS = (
    "Desktop" + "\\Frameworks\\" + _SRC,
    "Desktop" + "\\Frameworks\\" + _SRC + "-Lab",
    "Desktop" + "/Frameworks/" + _SRC,
    "Desktop" + "/Frameworks/" + _SRC + "-Lab",
)
FORBIDDEN_TERMS = (
    "phase6ev",
    "cohort",
    "recruitment",
    "guardian",
    "recurrence",
    "OPEN_AUTHORIZATION",
    "current-phase-docs",
    "architecture-decisions",
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\b(?:api[_-]?key|openai_api_key|openrouter_api_key)\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.I),
)

REQUIRED_FILES = (
    "src/pdl_taskmaster/controller/mechanical_controller.py",
    "src/pdl_taskmaster/runtime/session_engine.py",
    "src/pdl_taskmaster/runtime/workspace.py",
    "src/pdl_taskmaster/runtime/normative_store.py",
    "src/pdl_taskmaster/runtime/operation_bridge.py",
    "src/pdl_taskmaster/runtime/context_compiler.py",
    "src/pdl_taskmaster/runtime/standard_registry.py",
    "src/pdl_taskmaster/runtime/presentation.py",
    "src/pdl_taskmaster/runtime/semantic_observer.py",
    "contracts/CONTRACT_MANIFEST.json",
    "contracts/EXECUTION_CONTRACT.json",
    "confirm-with-pseudocode/SKILL.md",
    "src/pdl_taskmaster/host/repl.py",
    "src/pdl_taskmaster/host/app.py",
    "src/pdl_taskmaster/observation/session.py",
    "src/pdl_taskmaster/observation/records.py",
    "src/pdl_taskmaster/observation/sinks.py",
    "src/pdl_taskmaster/providers/base.py",
    "src/pdl_taskmaster/providers/recorded.py",
    "src/pdl_taskmaster/providers/fixtures.py",
    "src/pdl_taskmaster/providers/codex_worker.py",
    "src/pdl_taskmaster/providers/live_stub.py",
    "src/pdl_taskmaster/tracking/mlflow_sink.py",
    "src/pdl_taskmaster/tracking/log_live_session.py",
    "src/pdl_taskmaster/eval/run_qualified_batch.py",
    "src/pdl_taskmaster/eval/leak_scan.py",
    "src/pdl_taskmaster/eval/fidelity_scan.py",
    "README.md",
    "SOURCE_PROVENANCE.json",
)


def _fixture_dir() -> Path:
    """Resolve the recorded fixture directory.

    Precedence (mirrors the Brain/Hands pattern of S1's NormativeStore):
    1. PDLT_FIXTURES_PATH environment variable (points at the r4-recorded-worker dir).
    2. tests/fixtures vendored location (self-contained offline suite).
    3. Repository-relative vendored location (compat with pre-restructure checkouts).
    4. Sibling PDL-Standard-Archive external fixtures.
    """
    env = os.environ.get("PDLT_FIXTURES_PATH", "").strip()
    if env:
        return Path(env)
    vendored = ROOT / "tests" / "fixtures"
    if vendored.is_dir() and (vendored / "recorded-cases.json").is_file():
        return vendored
    local = ROOT / "fixtures" / "r4-recorded-worker"
    if local.is_dir():
        return local
    archive = ROOT.parent / "PDL-Standard-Archive" / "fixtures-r4-recorded-worker"
    if archive.is_dir():
        return archive
    return vendored



def _failures() -> list[str]:
    problems: list[str] = []

    # 1. Required runtime/instructional files.
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            problems.append(f"missing_required_file:{relative}")

    # 1b. Zero-template invariant (S2 / ADR-0008): the workspace template must NOT exist.
    if (ROOT / "workspace-template").exists():
        problems.append("zero_template_violation:workspace-template directory must be absent")

    # 1c. Clause-coverage invariant (D28): every clause defined in the normative
    # standards must be either bound in a contract or explicitly registered as
    # unbound. A clause added to a standards file without a contract binding
    # fails the verifier exactly like a code regression.
    defined: set[str] = set()
    for std_file in (ROOT / "contracts" / "standards").glob("*.md"):
        for m in re.finditer(r"\*\*([A-Z]+-\d+)(?:\s*[—-])", std_file.read_text(encoding="utf-8")):
            defined.add(m.group(1))
    bound: set[str] = set()
    for contract_name in ("EXECUTION_CONTRACT.json", "VERIFICATION_CONTRACT.json"):
        contract_data = json.loads((ROOT / "contracts" / contract_name).read_text(encoding="utf-8"))

        def _walk_requirements(node: object) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "requirements" and isinstance(value, list):
                        bound.update(x for x in value if isinstance(x, str) and re.match(r"^[A-Z]+-\d+$", x))
                    _walk_requirements(value)
            elif isinstance(node, list):
                for item in node:
                    _walk_requirements(item)

        _walk_requirements(contract_data)
    for clause in sorted(defined - bound):
        problems.append(f"clause_coverage_uncovered:{clause} defined in standards but not bound in any contract")

    # 1d. Subprocess script targets referenced by the REPL must exist.
    repl_path = ROOT / "src" / "pdl_taskmaster" / "host" / "repl.py"
    if repl_path.is_file():
        repl_text = repl_path.read_text(encoding="utf-8")
        import importlib.util
        for match in sorted(set(re.findall(r'-m",\s*"([^"]+)"', repl_text))):
            try:
                spec = importlib.util.find_spec(match)
                if spec is None or spec.origin is None:
                    problems.append(f"missing_repl_subprocess_module:{match}")
            except (ValueError, ModuleNotFoundError):
                problems.append(f"missing_repl_subprocess_module:{match}")

    # 2. Broken imports.
    try:
        from pdl_taskmaster.host.app import PDLtHost  # noqa: F401
        from pdl_taskmaster.host.repl import main as repl_main  # noqa: F401
        from pdl_taskmaster.runtime.session_engine import SessionEngine  # noqa: F401
        from pdl_taskmaster.providers.fixtures import build_recorded_fixture_from_vendored  # noqa: F401
    except Exception as exc:
        problems.append(f"import_failure:{exc}")

    # 3. External-source-repo leakage.
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.name == "SOURCE_PROVENANCE.json":
            continue  # provenance must record source repository paths by design
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for marker in SOURCE_REPO_MARKERS:
            if marker in text:
                problems.append(f"source_repo_path_leak:{path.relative_to(ROOT).as_posix()}")
                break
    for env_name in ("PYTHONPATH", "PYTHONHOME"):
        value = os.environ.get(env_name, "")
        for root in ("PDL-Standard-R2S", "PDL-Standard-R2S-Lab"):
            if root in value:
                problems.append(f"environment_leak:{env_name}={value}")

    # 4. Fixture integrity (externalized: PDLT_FIXTURES_PATH -> repo-relative fallback).
    fixture_dir = _fixture_dir()
    if not fixture_dir.is_dir():
        problems.append(
            "fixture_dir_missing:" + str(fixture_dir) + " (set PDLT_FIXTURES_PATH to the r4-recorded-worker archive directory)"
        )
        fixture = {}
        manifest = {}
    else:
        fixture_path = fixture_dir / "recorded-cases.json"
        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append(f"fixture_load_failure:{exc}")
            fixture = {}
        manifest = json.loads((fixture_dir / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8"))
    manifest_prompts = {entry["source_evidence_run"]: entry["prompt_sha256"] for entry in manifest.get("entries", [])}
    for entry in fixture.get("entries", []):
        expected = manifest_prompts.get(entry.get("source"))
        if expected is not None and entry.get("prompt_sha256") != expected:
            problems.append(f"fixture_hash_mismatch:{entry.get('source')}")

    # 5. Forbidden terms / secrets (classification; absolute source paths above are fatal).
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.name == "verify_repl_baseline.py":
            continue  # scanner's own source contains forbidden terms by definition
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"possible_secret:{path.relative_to(ROOT).as_posix()}")
        for term in FORBIDDEN_TERMS:
            if term in text:
                print(f"WARN forbidden-term {term!r} in {path.relative_to(ROOT).as_posix()}")

    return problems


def _fresh_workspace_lifecycle() -> dict[str, object]:
    from pdl_taskmaster.host.app import PDLtHost
    from pdl_taskmaster.providers.fixtures import build_recorded_fixture_from_vendored

    fixture_file = _fixture_dir() / "recorded-cases.json"
    fixture = json.loads(fixture_file.read_text(encoding="utf-8"))
    turns = fixture["case_turns"]["G06"]

    with tempfile.TemporaryDirectory(prefix="repl-baseline-") as tmp:
        tmp_root = Path(tmp)
        worker = build_recorded_fixture_from_vendored(ROOT, fixture_file, case_ids=["G06"])
        host = PDLtHost(
            ROOT,
            worker=worker,
            workspace_root=tmp_root / "workspaces",
            run_id="baseline",
            observation_dir=tmp_root / "observations",
        ).start()
        stages: list[str] = []
        try:
            for turn in turns:
                result = host.handle(turn)
                if result.state_after is not None:
                    stage = (result.state_after.get("controller_state") or {}).get("stage")
                    if stage:
                        stages.append(str(stage))
            status = host.status()
            workspace_path = Path(status["workspace_path"])
            final_stage = (status.get("controller_state") or {}).get("stage")
            from pdl_taskmaster.runtime.workspace import WorkspaceRun as _WR
            _ws = _WR.open(ROOT, workspace_path)
            _stages = _ws.stages_root()
            result_file = _stages / "50_execution" / "output" / "current.json"
            stage_dirs = sorted(p.name for p in _stages.iterdir() if p.is_dir())
            fresh_ok = "10_prompt" in stage_dirs and "30_plan" in stage_dirs and "50_execution" in stage_dirs
            if final_stage != "CLOSED_SUCCESS":
                raise AssertionError(f"final stage {final_stage!r} != CLOSED_SUCCESS")
            if not result_file.is_file():
                raise AssertionError("execution result file missing")
            if not fresh_ok:
                raise AssertionError("fresh workspace did not materialize stage directories")

            # Resume the newly-created workspace.
            worker2 = build_recorded_fixture_from_vendored(ROOT, fixture_file, case_ids=["G06"])
            resumed = PDLtHost(
                ROOT,
                worker=worker2,
                restore_path=workspace_path,
                run_id="baseline-resume",
                observation_dir=tmp_root / "observations-resume",
            ).start()
            resume_stage = (resumed.status().get("controller_state") or {}).get("stage")
            if resume_stage != "CLOSED_SUCCESS":
                raise AssertionError(f"resume stage {resume_stage!r} != CLOSED_SUCCESS")
            resumed.close()
        finally:
            host.close()
        return {"stages": stages, "final_stage": final_stage, "resume_stage": resume_stage, "fresh_workspace": fresh_ok}


def main() -> int:
    problems = _failures()
    lifecycle: dict[str, object] = {}
    if not problems:
        try:
            lifecycle = _fresh_workspace_lifecycle()
        except Exception as exc:
            problems.append(f"lifecycle_failure:{exc}")
    for problem in problems:
        print(f"FAIL {problem}")
    print("REPL BASELINE VERIFICATION", "PASS" if not problems else "FAIL")
    if lifecycle:
        print(json.dumps(lifecycle, indent=2, sort_keys=True))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())