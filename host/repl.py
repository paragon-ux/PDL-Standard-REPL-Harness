from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.app import PDLtHost
from providers.codex_worker import CodexWorker
from providers.fixtures import build_recorded_fixture, build_recorded_fixture_from_vendored


def _new_session_name() -> str:
    return datetime.now().strftime("session-%Y%m%d-%H%M%S")


_SESSION_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")


def sanitize_session_name(name: str) -> str:
    """Validate and normalize a user-supplied session identifier.

    Rejects empty/whitespace values, path separators, drive-qualified or
    absolute paths, traversal components, invalid Windows filename
    characters, control characters, and any name that could escape the
    session root.
    """
    value = (name or "").strip()
    if not value:
        raise ValueError("session name is empty")
    if len(value) > 120:
        raise ValueError("session name exceeds 120 characters")
    if value.startswith("."):
        raise ValueError("session name must not start with '.'")
    if value in {".", ".."}:
        raise ValueError("session name is a path component, not an identifier")
    if any(ch in value for ch in '<>:"|?*/\\'):
        raise ValueError("session name contains invalid path characters")
    if any(ord(ch) < 32 for ch in value):
        raise ValueError("session name contains control characters")
    if not _SESSION_NAME_RE.fullmatch(value):
        raise ValueError("session name may only contain letters, digits, '.', '_', '-'")
    return value


def resolve_session_dir(session_base: Path, session_id: str) -> Path:
    """Resolve a session directory and reject any path escaping the root."""
    safe = sanitize_session_name(session_id)
    base = session_base.resolve()
    candidate = (base / safe).resolve()
    if candidate != base and not candidate.is_relative_to(base):
        raise ValueError(f"session path escapes session root: {candidate}")
    return candidate


@dataclass
class SessionRuntime:
    """REPL bookkeeping only; never a parallel protocol state machine.

    Protocol authority remains SessionEngine + WorkspaceRun. This structure
    holds host/session lifetime bookkeeping so /new, /resume, and /worker
    cannot accidentally reselect a stale session.
    """

    session_id: str
    session_dir: Path
    host: PDLtHost
    session_pointer: Path
    transcript: TextIO
    transcript_path: Path
    workspace_root: Path
    observation_dir: Path

    def close(self) -> None:
        try:
            self.transcript.write("=== PDLt session ended ===\n")
            self.transcript.flush()
        finally:
            self.transcript.close()
            self.host.close()

    def _refresh_pointer(self) -> None:
        workspace_path = self.host.status().get("workspace_path")
        if workspace_path:
            self.session_pointer.write_text(
                json.dumps({"workspace_path": workspace_path}, indent=2) + "\n",
                encoding="utf-8",
            )

    def handle(self, user_message: str):
        """Dispatch a user turn, then refresh the durable session pointer.

        The workspace only materializes on the first protocol turn, so the
        pointer is written lazily after that workspace exists. This is
        bookkeeping only; protocol authority stays in SessionEngine/Workspace.
        """
        result = self.host.handle(user_message)
        self._refresh_pointer()
        return result


def _select_session(session_base: Path, args) -> str:
    if args.session_id:
        return sanitize_session_name(args.session_id)
    if args.new_session or not sys.stdin.isatty():
        return _new_session_name()
    sessions = sorted(
        (path for path in session_base.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if sessions:
        print("Existing sessions:", flush=True)
        for index, path in enumerate(sessions, 1):
            print(f"  {index}) {path.name}", flush=True)
        print("  n) Start a new session", flush=True)
    else:
        print("No existing sessions.", flush=True)
    try:
        choice = input("Select session: ").strip()
    except EOFError:
        return _new_session_name()
    if choice.isdigit() and 1 <= int(choice) <= len(sessions):
        return sessions[int(choice) - 1].name
    if choice.lower() == "n" or not choice:
        return _new_session_name()
    return sanitize_session_name(choice)


def open_session(
    args,
    session_base: Path,
    worker,
    session_id: str,
    restore_path: Path | None = None,
) -> SessionRuntime:
    session_dir = resolve_session_dir(session_base, session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    workspace_root = args.workspace_root or session_dir / "workspaces"
    observation_dir = args.observation_dir or session_dir / "observations"
    if hasattr(worker, "workdir"):
        worker.workdir = str(args.workdir or session_dir)
    pointer = session_dir / "session.json"
    if pointer.is_file() and restore_path is None:
        data = json.loads(pointer.read_text(encoding="utf-8"))
        stored = data.get("workspace_path")
        if stored and Path(stored).is_dir():
            restore_path = Path(stored)
    host = PDLtHost(
        args.candidate_repo,
        worker=worker,
        workspace_root=workspace_root,
        restore_path=restore_path,
        run_id=args.run_id,
        observation_dir=observation_dir,
    ).start()
    if host.status().get("workspace_path"):
        pointer.write_text(
            json.dumps({"workspace_path": host.status()["workspace_path"]}, indent=2) + "\n",
            encoding="utf-8",
        )
    transcript_path = args.transcript or session_dir / "transcript.log"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript = transcript_path.open("a", encoding="utf-8", newline="\n")
    return SessionRuntime(
        session_id=session_id,
        session_dir=session_dir,
        host=host,
        session_pointer=pointer,
        transcript=transcript,
        transcript_path=transcript_path,
        workspace_root=workspace_root,
        observation_dir=observation_dir,
    )


def switch_session(
    runtime: SessionRuntime,
    args,
    session_base: Path,
    worker,
    session_id: str,
    *,
    log_mlflow: bool,
) -> SessionRuntime:
    """Close the active host and open another session in one operation."""
    if log_mlflow:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "log_live_session.py"), "--session-dir", str(runtime.session_dir)],
            cwd=ROOT,
        )
    runtime.close()
    return open_session(args, session_base, worker, session_id)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="PDLt terminal REPL")
    parser.add_argument("--candidate-repo", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, default=None)
    parser.add_argument("--restore", type=Path, default=None)
    parser.add_argument("--run-id", default="repl")
    parser.add_argument("--observation-dir", type=Path, default=None)
    parser.add_argument("--worker", choices=["recorded", "codex"], default="codex")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--eval-root", type=Path, default=None)
    parser.add_argument("--evidence", type=Path, default=None)
    parser.add_argument("--case-ids", default=None)
    parser.add_argument("--session-id", default=None, help="reuse a named session workspace across invocations")
    parser.add_argument("--new-session", action="store_true", help="skip the session selector and start a new session")
    parser.add_argument("--transcript", type=Path, default=None, help="session-scoped transcript output file")
    parser.add_argument("--workdir", type=Path, default=None, help="writable session directory for the live worker")
    parser.add_argument("--mlflow", action="store_true", help="log the session to MLflow on exit")
    parser.add_argument("--worker-timeout", type=float, default=600.0, help="Codex worker timeout in seconds")
    parser.add_argument("--no-token-telemetry", action="store_true", help="disable worker token telemetry")
    parser.add_argument(
        "--worker-sandbox",
        choices=["read-only", "workspace-write"],
        default="read-only",
        help="Codex worker sandbox mode (default read-only for the semantic worker)",
    )
    parser.add_argument(
        "--allow-bypass",
        action="store_true",
        help="OPT-IN ONLY: use --dangerously-bypass-approvals-and-sandbox. Requires a hardened/disposable execution environment; not part of the Phase 0-5 seal.",
    )
    args = parser.parse_args()

    session_base = args.workspace_root or ROOT / "runs" / "live-sessions"
    try:
        session_id = _select_session(session_base, args)
    except ValueError as exc:
        print(f"[invalid session name] {exc}", flush=True)
        session_id = _new_session_name()
    session_dir = resolve_session_dir(session_base, session_id)
    log_mlflow = args.mlflow
    if not log_mlflow and sys.stdin.isatty():
        try:
            choice = input("Log this session to MLflow on exit? [y/N]: ").strip().lower()
        except EOFError:
            choice = ""
        log_mlflow = choice in {"y", "yes"}
    print(f"MLflow logging: {'on' if log_mlflow else 'off'}", flush=True)

    if args.worker == "recorded":
        if not args.eval_root and sys.stdin.isatty():
            args.eval_root = Path(input("eval-root: ").strip())
        if not args.evidence and sys.stdin.isatty():
            args.evidence = Path(input("evidence: ").strip())
        if not args.case_ids and sys.stdin.isatty():
            args.case_ids = input("case-ids (comma separated, optional): ").strip() or None
        if not args.evidence:
            raise SystemExit("--evidence is required for recorded worker")
        case_ids = [item.strip() for item in args.case_ids.split(",") if item.strip()] if args.case_ids else None
        if args.evidence.name == "recorded-cases.json":
            worker = build_recorded_fixture_from_vendored(
                args.candidate_repo,
                args.evidence,
                case_ids=case_ids,
            )
        else:
            if not args.eval_root:
                raise SystemExit("--eval-root is required for non-vendored recorded evidence")
            worker = build_recorded_fixture(
                args.candidate_repo,
                args.eval_root,
                args.evidence,
                case_ids=case_ids,
            )
    elif args.worker == "codex":
        worker = CodexWorker(
            model=args.model,
            workdir=args.workdir or session_dir,
            timeout=args.worker_timeout,
            progress_path=session_dir / "worker-progress.log",
            on_progress=lambda line: print(f"[codex] {line}", flush=True) if line.strip() else None,
            capture_tokens=not args.no_token_telemetry,
            allowed_workdir_root=session_base,
            sandbox_mode=args.worker_sandbox,
            allow_bypass=args.allow_bypass,
        )
    else:
        raise SystemExit(f"unsupported worker: {args.worker}")

    runtime = open_session(args, session_base, worker, session_id, restore_path=args.restore)

    def _write_transcript(text: str) -> None:
        runtime.transcript.write(text + "\n")
        runtime.transcript.flush()

    _write_transcript("=== PDLt session started ===")
    print("PDLt REPL started. Send normal text to the SessionEngine.", flush=True)
    print("WORKER: DEVELOPMENT / LIVE DEMONSTRATION; NOT A QUALIFIED R2S MEASUREMENT CONDITION", flush=True)
    if args.allow_bypass:
        print(
            "WARNING: dangerous bypass mode is ON. This condition requires an externally "
            "hardened/disposable environment and is NOT part of the Phase 0-5 seal.",
            flush=True,
        )
    print("Commands: /status /help /quit", flush=True)
    _write_transcript("WORKER: DEVELOPMENT / LIVE DEMONSTRATION; NOT A QUALIFIED R2S MEASUREMENT CONDITION")
    try:
        while True:
            sys.stdout.flush()
            line = input("> ").strip()
            _write_transcript("USER> " + line)
            if line == "/quit":
                break
            if line == "/help":
                print(
                    "normal text -> SessionEngine\n"
                    "/status -> read-only host state\n"
                    "/session -> current session directory\n"
                    "/mlflow [on|off] -> toggle MLflow logging\n"
                    "/tokens [on|off] -> toggle token telemetry\n"
                    "/timeout [seconds] -> show/set worker timeout\n"
                    "/model [name] -> show/set worker model\n"
                    "/worker [codex|recorded] -> switch worker\n"
                    "/sandbox [read-only|workspace-write] -> show/set worker sandbox mode\n"
                    "/workdir [path] -> show/set worker workdir\n"
                    "/transcript [path] -> show/set transcript file\n"
                    "/new -> start a new session\n"
                    "/resume <session-id> -> resume a session\n"
                    "/quit -> exit",
                    flush=True,
                )
                continue
            if line == "/status":
                print(runtime.host.status(), flush=True)
                continue
            if line.startswith("/"):
                parts = line.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1].strip() if len(parts) > 1 else ""
                if cmd == "/mlflow":
                    if arg in {"on", "off"}:
                        log_mlflow = arg == "on"
                    else:
                        log_mlflow = not log_mlflow
                    print(f"MLflow logging: {'on' if log_mlflow else 'off'}", flush=True)
                elif cmd == "/timeout":
                    if not arg:
                        timeout = getattr(worker, "timeout", None)
                        print(f"worker timeout: {timeout}s" if timeout is not None else "worker timeout: n/a for this worker", flush=True)
                    else:
                        try:
                            worker.timeout = float(arg)
                            print(f"worker timeout set to {worker.timeout}s", flush=True)
                        except (AttributeError, ValueError) as exc:
                            print(f"cannot set timeout: {exc}", flush=True)
                elif cmd == "/model":
                    if not arg:
                        model = getattr(worker, "model", None)
                        print(f"model: {model}" if model is not None else "model: n/a for this worker", flush=True)
                    else:
                        try:
                            worker.model = arg
                            print(f"model set to {worker.model}", flush=True)
                        except (AttributeError, ValueError) as exc:
                            print(f"cannot set model: {exc}", flush=True)
                elif cmd == "/sandbox":
                    if not arg:
                        sandbox = getattr(worker, "sandbox_mode", None)
                        print(f"sandbox mode: {sandbox}" if sandbox is not None else "sandbox mode: n/a for this worker", flush=True)
                    elif arg in {"read-only", "workspace-write"}:
                        try:
                            worker.sandbox_mode = arg
                            print(f"sandbox mode set to {worker.sandbox_mode}", flush=True)
                        except (AttributeError, ValueError) as exc:
                            print(f"cannot set sandbox mode: {exc}", flush=True)
                    else:
                        print("usage: /sandbox [read-only|workspace-write]", flush=True)
                elif cmd == "/workdir":
                    if not arg:
                        workdir = getattr(worker, "workdir", None)
                        print(f"workdir: {workdir}" if workdir is not None else "workdir: n/a for this worker", flush=True)
                    else:
                        try:
                            target = Path(arg).resolve()
                            allowed = session_base.resolve()
                            if target != allowed and not target.is_relative_to(allowed):
                                print(f"workdir must stay inside {allowed}", flush=True)
                            else:
                                worker.workdir = str(target)
                                print(f"workdir set to {worker.workdir}", flush=True)
                        except (AttributeError, ValueError) as exc:
                            print(f"cannot set workdir: {exc}", flush=True)
                elif cmd == "/transcript":
                    if arg:
                        runtime.transcript.close()
                        transcript_path = Path(arg)
                        transcript_path.parent.mkdir(parents=True, exist_ok=True)
                        runtime.transcript = transcript_path.open("a", encoding="utf-8", newline="\n")
                        runtime.transcript_path = transcript_path
                        print(f"transcript set to {transcript_path}", flush=True)
                    else:
                        print(f"transcript: {runtime.transcript_path}", flush=True)
                elif cmd == "/session":
                    print(f"session: {runtime.session_dir}", flush=True)
                elif cmd == "/tokens":
                    if arg in {"on", "off"}:
                        worker.capture_tokens = arg == "on"
                    else:
                        worker.capture_tokens = not getattr(worker, "capture_tokens", False)
                    print(f"token telemetry: {'on' if getattr(worker, 'capture_tokens', False) else 'off'}", flush=True)
                elif cmd == "/worker":
                    target = arg or "codex"
                    if target == "codex":
                        new_worker = CodexWorker(
                            model=args.model,
                            workdir=runtime.session_dir,
                            timeout=args.worker_timeout,
                            progress_path=runtime.session_dir / "worker-progress.log",
                            on_progress=lambda line: print(f"[codex] {line}", flush=True) if line.strip() else None,
                            capture_tokens=getattr(worker, "capture_tokens", True),
                            allowed_workdir_root=session_base,
                            sandbox_mode=getattr(worker, "sandbox_mode", args.worker_sandbox),
                            allow_bypass=getattr(worker, "allow_bypass", args.allow_bypass),
                        )
                    elif target == "recorded":
                        if not args.eval_root or not args.evidence:
                            if not sys.stdin.isatty():
                                print("recorded worker requires --eval-root and --evidence in non-interactive mode", flush=True)
                                continue
                            eval_root = input("eval-root: ").strip()
                            evidence = input("evidence: ").strip()
                        else:
                            eval_root = str(args.eval_root)
                            evidence = str(args.evidence)
                        case_ids = args.case_ids
                        if not case_ids and sys.stdin.isatty():
                            case_ids = input("case-ids (comma separated, optional): ").strip() or None
                        case_ids_list = [item.strip() for item in case_ids.split(",") if item.strip()] if case_ids else None
                        new_worker = build_recorded_fixture(
                            args.candidate_repo,
                            Path(eval_root),
                            Path(evidence),
                            case_ids=case_ids_list,
                        )
                    else:
                        print(f"unknown worker: {target}", flush=True)
                        continue
                    runtime = switch_session(
                        runtime, args, session_base, new_worker, runtime.session_id, log_mlflow=log_mlflow
                    )
                    worker = new_worker
                    print(f"worker switched to {target}", flush=True)
                elif cmd == "/new":
                    runtime = switch_session(
                        runtime, args, session_base, worker, _new_session_name(), log_mlflow=log_mlflow
                    )
                    print(f"new session: {runtime.session_dir}", flush=True)
                elif cmd == "/resume":
                    if not arg:
                        print("usage: /resume <session-id>", flush=True)
                        continue
                    try:
                        safe_id = sanitize_session_name(arg)
                    except ValueError as exc:
                        print(f"invalid session name: {exc}", flush=True)
                        continue
                    runtime = switch_session(runtime, args, session_base, worker, safe_id, log_mlflow=log_mlflow)
                    print(f"resumed session: {runtime.session_dir}", flush=True)
                else:
                    print(f"unknown command: {cmd}", flush=True)
                continue
            print("[working...]", flush=True)
            print(f"[worker progress -> {runtime.session_dir / 'worker-progress.log'}]", flush=True)
            try:
                turn = runtime.handle(line)
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                print(f"[error] {message}", flush=True)
                _write_transcript("ERROR> " + message)
                continue
            if turn.text:
                print(turn.text, flush=True)
                _write_transcript("ASSISTANT> " + turn.text)
            if turn.closed:
                print("[protocol closed]", flush=True)
                _write_transcript("PROTOCOL_CLOSED")
    finally:
        runtime.close()
        if log_mlflow:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "log_live_session.py"),
                    "--session-dir",
                    str(runtime.session_dir),
                ],
                cwd=ROOT,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
