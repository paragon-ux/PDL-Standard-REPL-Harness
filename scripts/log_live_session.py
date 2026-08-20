from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mlflow
from tracking.mlflow_sink import log_experiment_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Log one live PDLt session to MLflow")
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--run-name", default=None)
    args = parser.parse_args()

    session_dir = args.session_dir.resolve()
    session_json = session_dir / "session.json"
    if not session_json.is_file():
        raise SystemExit(f"session.json missing: {session_json}")
    session_data = json.loads(session_json.read_text(encoding="utf-8"))
    session_id = session_dir.name

    observation_files = sorted((session_dir / "observations").glob("*.jsonl")) if (session_dir / "observations").is_dir() else []
    observation_records = 0
    final_stage = None
    total_tokens = 0
    for obs in observation_files:
        rows = [json.loads(line) for line in obs.read_text(encoding="utf-8").splitlines() if line.strip()]
        observation_records += len(rows)
        if rows:
            final_stage = ((rows[-1].get("controller_after") or {}).get("controller_state") or {}).get("stage")
        for row in rows:
            for call in row.get("calls", []):
                usage = call.get("usage") or {}
                total_tokens += int(usage.get("total_tokens") or 0)

    transcript = session_dir / "transcript.log"
    artifacts = [str(session_json)]
    if transcript.is_file():
        artifacts.append(str(transcript))
    artifacts.extend(str(path) for path in observation_files)

    mlflow.set_tracking_uri(f"sqlite:///{(ROOT / 'mlflow.db').as_posix()}")
    mlflow.set_experiment("PDL-R2S")
    run_id = log_experiment_run(
        args.run_name or f"live-session-{session_id}",
        params={
            "run_type": "live_session",
            "session_id": session_id,
            "candidate_repository": "PDL-Standard-R2S",
            "candidate_commit": "6df3bf5733cd3fcd16b1560ff7a80810c96bbe6c",
            "worker_profile": "codex",
            "observation_jsonl_path": ",".join(str(path) for path in observation_files),
            "transcript_path": str(transcript) if transcript.is_file() else "none",
            "workspace_path": str(session_data.get("workspace_path", "none")),
            "final_stage": final_stage or "unknown",
        },
        metrics={"observation_records": float(observation_records), "total_tokens": float(total_tokens)},
        artifacts=artifacts,
    )
    print(f"LIVE_SESSION_MLFLOW_RUN {run_id} session={session_id} records={observation_records}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
