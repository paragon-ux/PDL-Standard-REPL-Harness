"""PDLt Live REPL Viewer & Telemetry Dashboard Server (Approach 1).

Lightweight HTTP/SSE server streaming REPL execution telemetry, worker logs,
Plane 1 Pydantic wire schemas, and Plane 2 ExecutionSandbox witness verifications
in real-time.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PDLT_TEST_ROOT = Path(r"C:\Users\USER\Desktop\Frameworks\PDLt-Test")
SESSIONS_DIR = REPO_ROOT / "runs" / "live-sessions"


def get_latest_session_dir() -> Path | None:
    if not SESSIONS_DIR.is_dir():
        return None
    sessions = sorted(
        [p for p in SESSIONS_DIR.iterdir() if p.is_dir() and p.name.startswith("session-")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return sessions[0] if sessions else None


def get_session_telemetry(session_dir: Path | None = None) -> dict[str, Any]:
    if session_dir is None:
        session_dir = get_latest_session_dir()
    if session_dir is None or not session_dir.is_dir():
        return {
            "session_id": "NONE",
            "stage": "IDLE",
            "active": False,
            "prompt": None,
            "plan": None,
            "active_prompt_name": None,
            "execution": None,
            "witness": None,
            "logs": [],
        }

    # Find active workspace
    ws_dir = session_dir / "workspaces"
    state_file = None
    latest_ws = None
    if ws_dir.is_dir():
        ws_subdirs = [p for p in ws_dir.iterdir() if p.is_dir()]
        if ws_subdirs:
            latest_ws = sorted(ws_subdirs, key=lambda p: p.stat().st_mtime, reverse=True)[0]
            candidate_state = latest_ws / "turns" / "turn_001" / "state" / "controller-state.json"
            if candidate_state.is_file():
                state_file = candidate_state

    controller_state = {}
    if state_file and state_file.is_file():
        try:
            controller_state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    stage = controller_state.get("stage", "PROMPT_REVIEW")
    current_prompt = controller_state.get("current_prompt", {}).get("body") if controller_state.get("current_prompt") else None
    current_plan = controller_state.get("current_plan", {}).get("body") if controller_state.get("current_plan") else None

    # Identify active prompt name
    active_prompt_name = None
    if latest_ws:
        raw_content_file = latest_ws / "turns" / "turn_001" / "stages" / "10_prompt" / "input" / "0001-bootstrap_analysis" / "raw_untrusted_content.md"
        if raw_content_file.is_file():
            try:
                raw_text = raw_content_file.read_text(encoding="utf-8", errors="replace").strip()
                active_prompt_name = raw_text.splitlines()[0][:60]
            except Exception:
                pass

    # Transcript / progress log tail
    transcript_file = session_dir / "transcript.log"
    logs = []
    if transcript_file.is_file():
        try:
            lines = transcript_file.read_text(encoding="utf-8", errors="replace").splitlines()
            logs = lines[-120:]
        except Exception:
            pass

    # Check for sandbox witness / execution files
    witness_data = None
    code_snippet = None
    if latest_ws:
        exec_out_dir = latest_ws / "turns" / "turn_001" / "stages" / "50_execution" / "output"
        if exec_out_dir.is_dir():
            model_resp_files = sorted(exec_out_dir.rglob("model-response.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
            if model_resp_files:
                try:
                    resp_text = model_resp_files[0].read_text(encoding="utf-8", errors="replace")
                    if "```python" in resp_text:
                        py_match = re.search(r"```python\s*\n(.*?)```", resp_text, re.S)
                        if py_match:
                            code_snippet = py_match.group(1).strip()
                    try:
                        resp_json = json.loads(resp_text)
                        witness_data = resp_json.get("result_ir", {}).get("witness") or resp_json.get("witness")
                    except Exception:
                        pass
                except Exception:
                    pass

    return {
        "session_id": session_dir.name,
        "stage": stage,
        "active": True,
        "prompt": current_prompt,
        "plan": current_plan,
        "active_prompt_name": active_prompt_name,
        "code_snippet": code_snippet,
        "witness": witness_data,
        "logs": logs,
    }


def get_catalogue_summary() -> list[dict[str, Any]]:
    prompts_dir = PDLT_TEST_ROOT / "prompts"
    if not prompts_dir.is_dir():
        return []
    items = []
    category_dirs = sorted([d for d in prompts_dir.iterdir() if d.is_dir() and d.name != "solutions"])
    for cat in category_dirs:
        txt_files = sorted(cat.glob("*.txt"))
        for f in txt_files:
            items.append({
                "id": f"{cat.name}/{f.stem}",
                "category": cat.name,
                "name": f.name,
                "path": str(f),
            })
    return items


class ThreadingViewerServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc_type, exc_val, exc_tb = sys.exc_info()
        if exc_type in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
        super().handle_error(request, client_address)


class REPLViewerHandler(http.server.SimpleHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def log_message(self, format, *args):
        # Suppress routine HTTP request log spam in console
        pass

    def do_GET(self):
        try:
            url_path = self.path.split("?")[0]

            if url_path in {"/", "/index.html", "/repl_viewer.html"}:
                html_path = Path(__file__).parent / "repl_viewer.html"
                if html_path.is_file():
                    content = html_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(content)
                    return

            if url_path == "/api/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                telemetry = get_session_telemetry()
                self.wfile.write(json.dumps(telemetry, ensure_ascii=False).encode("utf-8"))
                return

            if url_path == "/api/catalogue":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                catalogue = get_catalogue_summary()
                self.wfile.write(json.dumps(catalogue, ensure_ascii=False).encode("utf-8"))
                return

            self.send_error(404, "File Not Found")
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass


def start_server(port: int = 8090) -> tuple[threading.Thread, socketserver.TCPServer, int]:
    handler = REPLViewerHandler
    server = None
    actual_port = port
    for p in range(port, port + 10):
        try:
            server = ThreadingViewerServer(("0.0.0.0", p), handler)
            actual_port = p
            break
        except OSError:
            continue
    if server is None:
        raise OSError("Could not bind viewer server to any port in range.")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread, server, actual_port


def main(argv: list[str] | None = None) -> int:
    import argparse
    import webbrowser

    parser = argparse.ArgumentParser(
        prog="pdlt viewer",
        description="Launch PDLt Live REPL Telemetry & Verification Dashboard Server.",
    )
    parser.add_argument("--port", "-p", type=int, default=8090, help="starting port to bind (default: 8090)")
    parser.add_argument("--no-open", action="store_true", help="do not automatically open dashboard in browser")
    args = parser.parse_args(argv)

    try:
        thread, server, bound_port = start_server(args.port)
    except OSError as exc:
        print(f"[error] Failed to start viewer server: {exc}", file=sys.stderr, flush=True)
        return 1

    url = f"http://localhost:{bound_port}"
    print(f"PDLt Live REPL Telemetry & Verification Viewer running on {url}", flush=True)
    print("Press CTRL + C to stop server.", flush=True)

    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping viewer server...", flush=True)
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

