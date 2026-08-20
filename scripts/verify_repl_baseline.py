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


ROOT = Path(__file__).resolve().parents[1]
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
    "controller/mechanical_controller.py",
    "runtime/session_engine.py",
    "runtime/workspace.py",
    "runtime/operation_bridge.py",
    "runtime/context_compiler.py",
    "runtime/standard_registry.py",
    "runtime/presentation.py",
    "runtime/semantic_observer.py",
    "contracts/CONTRACT_MANIFEST.json",
    "contracts/EXECUTION_CONTRACT.json",
    "workspace-template/stages/00_activation/CONTEXT.md",
    "workspace-template/stages/10_prompt/CONTEXT.md",
    "workspace-template/stages/30_plan/CONTEXT.md",
    "workspace-template/stages/50_execution/CONTEXT.md",
    "confirm-with-pseudocode/SKILL.md",
    "host/repl.py",
    "host/app.py",
    "observation/session.py",
    "observation/records.py",
    "observation/sinks.py",
    "providers/base.py",
    "providers/recorded.py",
    "providers/fixtures.py",
    "providers/codex_worker.py",
    "providers/live_stub.py",
    "tracking/mlflow_sink.py",
    "scripts/log_live_session.py",
    "fixtures/r4-recorded-worker/recorded-cases.json",
    "fixtures/r4-recorded-worker/FIXTURE_MANIFEST.json",
    "README.md",
    "SOURCE_PROVENANCE.json",
)


def _failures() -> list[str]:
    problems: list[str] = []

    # 1. Required runtime/instructional files.
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            problems.append(f"missing_required_file:{relative}")

    # 1b. Subprocess script targets referenced by the REPL must exist.
    repl_text = (ROOT / "host" / "repl.py").read_text(encoding="utf-8")
    for match in re.findall(r'ROOT / "scripts" / "([^"]+)"', repl_text):
        if not (ROOT / "scripts" / match).is_file():
            problems.append(f"missing_repl_subprocess_script:scripts/{match}")

    # 2. Broken imports.
    try:
        from host.app import PDLtHost  # noqa: F401
        from host.repl import main as repl_main  # noqa: F401
        from runtime.session_engine import SessionEngine  # noqa: F401
        from providers.fixtures import build_recorded_fixture_from_vendored  # noqa: F401
    except Exception as exc:
        problems.append(f"import_failure:{exc}")

    # 3. External-source-repo leakage.
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
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

    # 4. Fixture integrity.
    fixture_path = ROOT / "fixtures" / "r4-recorded-worker" / "recorded-cases.json"
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except Exception as exc:
        problems.append(f"fixture_load_failure:{exc}")
        fixture = {}
    manifest = json.loads((ROOT / "fixtures" / "r4-recorded-worker" / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8"))
    manifest_prompts = {entry["source_evidence_run"]: entry["prompt_sha256"] for entry in manifest.get("entries", [])}
    for entry in fixture.get("entries", []):
        expected = manifest_prompts.get(entry.get("source"))
        if expected is not None and entry.get("prompt_sha256") != expected:
            problems.append(f"fixture_hash_mismatch:{entry.get('source')}")

    # 5. Forbidden terms / secrets (classification; absolute source paths above are fatal).
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
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
    from host.app import PDLtHost
    from providers.fixtures import build_recorded_fixture_from_vendored

    fixture_file = ROOT / "fixtures" / "r4-recorded-worker" / "recorded-cases.json"
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
            result_file = workspace_path / "stages" / "50_execution" / "output" / "current.json"
            stage_dirs = sorted(p.name for p in (workspace_path / "stages").iterdir() if p.is_dir())
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