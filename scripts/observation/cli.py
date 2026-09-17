from __future__ import annotations

import argparse
import json
from pathlib import Path


def _show(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        before = record.get("controller_before") or {}
        after = record.get("controller_after") or {}
        before_stage = (before.get("controller_state") or {}).get("stage")
        after_stage = (after.get("controller_state") or {}).get("stage")
        print(f"turn={record.get('turn_index')} {before_stage} -> {after_stage}")
        for call in record.get("calls", []):
            parsed = call.get("parsed")
            if call.get("parse_error"):
                parsed_summary = f"parse_error={call['parse_error']}"
            else:
                parsed_summary = json.dumps(parsed, sort_keys=True, default=str)[:300]
            print(
                f"  {call.get('operation')} prompt={call.get('prompt_sha256')[:12]} "
                f"response={call.get('response_sha256')[:12]} parsed={parsed_summary}"
            )
        event_kinds = [event.get("kind") for event in record.get("events", {}).get("new", [])]
        if event_kinds:
            print(f"  events={event_kinds}")
        if record.get("exception"):
            print(f"  exception={record['exception']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PDL-R2S observation viewer")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", help="show recorded turns")
    show.add_argument("--session", required=True, type=Path, help="path to session JSONL")
    args = parser.parse_args()
    if args.command == "show":
        _show(args.session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
