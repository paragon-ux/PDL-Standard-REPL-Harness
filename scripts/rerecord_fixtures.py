"""Re-record the vendored replay fixtures under the protocol v2 flow.

Always-on semantic-bootstrap separation changes the op sequence for every
session (BOOTSTRAP_ANALYSIS now precedes DRAFT_PROMPT/REVISE_*), so recorded
prompt hashes change. This script replays the fixture case scripts through the
real engine with a recording wrapper around LiveStubWorker and rewrites:
  fixtures/r4-recorded-worker/recorded-cases.json   (entries + case_turns)
  fixtures/r4-recorded-worker/FIXTURE_MANIFEST.json (source->hash manifest)

Deterministic: LiveStubWorker responses are canned, so hashes are stable across
runs and machines (prompts contain no timestamps; workspace ids are random but
not rendered into prompts).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.app import DEFAULT_HIGHER_PRIORITY_CONSTRAINTS  # noqa: E402
from providers.live_stub import LiveStubWorker  # noqa: E402
from runtime.operation_bridge import ModelRequest  # noqa: E402
from runtime.session_engine import SessionEngine  # noqa: E402

FIXTURE_DIR = ROOT / "fixtures" / "r4-recorded-worker"


class RecordingStub:
    def __init__(self) -> None:
        self.inner = LiveStubWorker()
        self.records: list[dict] = []

    def call(self, request: ModelRequest) -> WorkerResult:
        result = self.inner.call(request)
        self.records.append(
            {
                "operation": request.operation,
                "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
                "prompt_text": request.prompt,
                "response": result.text,
            }
        )
        return result


def record_case(case_id: str, turns: list[str], cache: dict) -> list[dict]:
    engine = SessionEngine(ROOT, model_call=cache["recorder"].call, workspace_root=cache["ws_root"])
    for turn in turns:
        engine.handle_user_message(turn)
    # close out any open stage (mirror original recordings which ran to completion)
    return [dict(r, source=f"{case_id}:{i:04d}-{slug(r['operation'])}") for i, r in enumerate(cache["recorder"].records, start=1)]


def slug(op: str) -> str:
    return op.lower().replace("_", "_")


def main() -> None:
    fixture = json.loads((FIXTURE_DIR / "recorded-cases.json").read_text(encoding="utf-8"))
    cases = fixture["cases"]
    all_entries: list[dict] = []
    for case_id in cases:
        recorder = RecordingStub()
        turns = fixture["case_turns"][case_id]
        # Run turn script; for G06 the third turn confirms and executes.
        engine = SessionEngine(
            ROOT,
            model_call=lambda req, _rec=recorder: _rec.call(req).text,
            workspace_root=FIXTURE_DIR.parent / "_rerecord-tmp",
            higher_priority_constraints=DEFAULT_HIGHER_PRIORITY_CONSTRAINTS,
            available_execution_tools=[],
        )
        for turn in turns:
            engine.handle_user_message(turn)
        stage = (engine.controller.state.stage if engine.controller else None)
        if stage is not None and stage not in {"CLOSED_SUCCESS", "CLOSED_CANCELLED"}:
            # drive remaining gates the way the original evidence sessions did
            for _ in range(6):
                stage = (engine.controller.state.stage if engine.controller else None)
                if stage in {"CLOSED_SUCCESS", "CLOSED_CANCELLED", None}:
                    break
                engine.handle_user_message("Confirm the plan and execute.")
        entries = [
            {
                "operation": r["operation"],
                "prompt_sha256": r["prompt_sha256"],
                "prompt_text": r["prompt_text"],
                "response": r["response"],
                "source": f"{case_id}:{i:04d}-{r['operation'].lower()}",
            }
            for i, r in enumerate(recorder.records, start=1)
        ]
        all_entries.extend(entries)

    # Deduplicate only exact duplicates within the same case: the replay CLI
    # filters entries by case prefix, so identical benign prompts across cases
    # must remain as separate per-case entries (same key+response is fine for
    # the replay mapping).
    seen: dict[tuple[str, str, str], dict] = {}
    for e in all_entries:
        seen[(e["source"].split(":")[0], e["operation"], e["prompt_sha256"])] = e
    deduped = list(seen.values())

    fixture["entries"] = deduped
    fixture["source_evidence"] = "re-recorded under protocol v2 semantic-bootstrap flow (docs/protocol-v2-semantic-bootstrap-spec.md)"
    fixture["schema"] = 1
    (FIXTURE_DIR / "recorded-cases.json").write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")

    manifest_entries = []
    for e in deduped:
        manifest_entries.append(
            {
                "source_evidence_run": e["source"],
                "operation": e["operation"],
                "prompt_sha256": e["prompt_sha256"],
                "raw_response_sha256": hashlib.sha256(e["response"].encode("utf-8")).hexdigest(),
                "fixture_id": hashlib.sha256(f"{e['source']}|{e['operation']}|{e['prompt_sha256']}".encode("utf-8")).hexdigest()[:16],
            }
        )
    manifest = {
        "schema": 1,
        "fixture_set": "r4-recorded-worker-vendored",
        "count": len(manifest_entries),
        "entries": manifest_entries,
    }
    (FIXTURE_DIR / "FIXTURE_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"re-recorded {len(deduped)} entries across {len(cases)} cases")


if __name__ == "__main__":
    main()
