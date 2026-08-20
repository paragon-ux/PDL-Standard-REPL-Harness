from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from providers.base import TransportError, WorkerResult


class CodexWorker:
    """LIVE SEMANTIC WORKER backed by the Codex CLI.

    This adapter is a semantic worker only. It is NOT a coding domain
    execution backend: it does not own PDL wire validity, controller routing,
    or filesystem artifact production on behalf of the candidate.

    Label: DEVELOPMENT / LIVE DEMONSTRATION WORKER
    NOT A QUALIFIED R2S MEASUREMENT CONDITION.

    Safety defaults (normal local operation):
        approval mode   = never
        sandbox mode    = read-only
        dangerous bypass = OFF

    The bypass condition is a separate, explicitly opt-in execution
    environment intended only for externally hardened/disposable runners. It
    is never used as an automatic fallback.
    """

    def __init__(
        self,
        *,
        model: str = "deepseek-v4-flash",
        workdir: str | Path | None = None,
        allowed_workdir_root: str | Path | None = None,
        timeout: float = 600.0,
        progress_path: str | Path | None = None,
        on_progress: Callable[[str], None] | None = None,
        capture_tokens: bool = True,
        sandbox_mode: str = "read-only",
        approval_policy: str = "never",
        allow_bypass: bool = False,
        json_mode: bool | None = None,
    ):
        if sandbox_mode not in {"read-only", "workspace-write"}:
            raise ValueError(f"unsupported sandbox mode: {sandbox_mode}")
        if approval_policy not in {"never"}:
            raise ValueError(f"unsupported approval policy: {approval_policy}")
        initial_workdir = str(Path(workdir).resolve()) if workdir else str(Path.cwd().resolve())
        self.model = model
        self.timeout = timeout
        self.progress_path = Path(progress_path) if progress_path else None
        self.on_progress = on_progress
        self.capture_tokens = capture_tokens
        self.sandbox_mode = sandbox_mode
        self.approval_policy = approval_policy
        self.allow_bypass = allow_bypass
        self.json_mode = capture_tokens if json_mode is None else json_mode
        self.allowed_workdir_root = str(
            Path(allowed_workdir_root).resolve() if allowed_workdir_root else Path(initial_workdir).resolve()
        )
        self.workdir = initial_workdir
        self.codex_cli_version = self._detect_version()

    @staticmethod
    def _detect_version() -> str:
        try:
            proc = subprocess.run(
                ["codex", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            return (proc.stdout or proc.stderr or "").strip() or "unknown"
        except Exception:
            return "unknown"

    @property
    def workdir(self) -> str:
        return self._workdir

    @workdir.setter
    def workdir(self, value: str | Path) -> None:
        resolved = str(Path(value).resolve())
        allowed = Path(self.allowed_workdir_root).resolve()
        candidate = Path(resolved).resolve()
        if candidate != allowed and not candidate.is_relative_to(allowed):
            raise ValueError(f"workdir must stay inside allowed root {allowed}: {resolved}")
        self._workdir = resolved

    @staticmethod
    def _format_progress(line: str, json_mode: bool) -> str:
        if not json_mode or not line.startswith("{"):
            return line
        try:
            event = json.loads(line)
        except Exception:
            return line
        event_type = event.get("type") or "event"
        payload = event.get("payload")
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("text")
            if isinstance(message, str) and message.strip():
                message = message.strip().replace("\n", " ")
                if len(message) > 240:
                    message = message[:237] + "..."
                return f"{event_type}: {message}"
        return event_type

    def call(self, request: Any) -> WorkerResult:
        prompt = (
            request.prompt
            + "\n\nReturn only a JSON object. Do not include markdown fences, commentary, or extra text."
        )
        fd, output_path = tempfile.mkstemp(prefix="codex-worker-", suffix=".txt")
        os.close(fd)
        output_lines: list[str] = []
        started = time.perf_counter()
        try:
            Path(self.workdir).mkdir(parents=True, exist_ok=True)
            cmd = [
                "codex",
                "exec",
                "-o",
                output_path,
                "--ephemeral",
                "--skip-git-repo-check",
                "-C",
                self.workdir,
                "-m",
                self.model,
            ]
            if self.allow_bypass:
                # Separate hardened/disposable execution condition only.
                cmd.append("--dangerously-bypass-approvals-and-sandbox")
            else:
                cmd += ["--sandbox", self.sandbox_mode, "-c", 'approval_policy="never"']
                if self.json_mode:
                    cmd.append("--json")
            cmd.append(prompt)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            def _stream() -> None:
                assert proc.stdout is not None
                for line in proc.stdout:
                    text_line = line.rstrip()
                    output_lines.append(text_line)
                    if self.progress_path is not None:
                        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
                        with self.progress_path.open("a", encoding="utf-8", newline="\n") as handle:
                            handle.write(text_line + "\n")
                    if self.on_progress is not None:
                        try:
                            display = self._format_progress(text_line, self.json_mode)
                            if display.strip():
                                self.on_progress(display)
                        except Exception:
                            pass

            thread = threading.Thread(target=_stream, daemon=True)
            thread.start()
            try:
                proc.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                thread.join(timeout=5)
                raise TransportError(f"Codex worker timed out after {self.timeout}s") from exc
            thread.join(timeout=5)
            if proc.returncode != 0:
                raise TransportError(
                    f"Codex exec failed rc={proc.returncode}; see progress log for details"
                )
            text = Path(output_path).read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                raise TransportError("Codex returned an empty worker response")

            latency_ms = (time.perf_counter() - started) * 1000.0
            usage, usage_source, usage_exact, response_id, observed_model = self._parse_telemetry(output_lines)
            metadata: dict[str, Any] = {
                "worker": "codex",
                "model": self.model,
                "observed_model": observed_model,
                "mode": "live-demonstration",
                "not_a_qualified_measurement_condition": True,
                "sandbox_mode": "bypass" if self.allow_bypass else self.sandbox_mode,
                "approval_mode": "bypass" if self.allow_bypass else self.approval_policy,
                "codex_cli_version": self.codex_cli_version,
                "workdir": self.workdir,
                "json_mode": self.json_mode,
                "response_id": response_id,
                "latency_ms": round(latency_ms, 3),
                "usage_source": usage_source,
                "usage_exact": usage_exact,
                "token_telemetry": "enabled" if self.capture_tokens else "disabled",
            }
            if usage:
                metadata["usage"] = usage
                metadata["codex_cli_reported_total"] = usage.get("codex_cli_reported_total")
            return WorkerResult(text, metadata)
        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    def _parse_telemetry(self, output_lines: list[str]) -> tuple[dict[str, Any] | None, str | None, bool, str | None, str | None]:
        usage: dict[str, Any] | None = None
        usage_source: str | None = None
        usage_exact = False
        response_id: str | None = None
        observed_model: str | None = None

        if self.capture_tokens and self.json_mode:
            for line in output_lines:
                if not line.startswith("{"):
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                candidate: dict[str, Any] | None = None
                if isinstance(event.get("usage"), dict):
                    candidate = event["usage"]
                elif isinstance(payload.get("usage"), dict):
                    candidate = payload["usage"]
                if candidate is not None:
                    structured: dict[str, Any] = {}
                    for key, value in candidate.items():
                        if isinstance(value, (int, float)) and key in {
                            "input_tokens",
                            "output_tokens",
                            "total_tokens",
                            "prompt_tokens",
                            "completion_tokens",
                            "reasoning_tokens",
                            "cached_input_tokens",
                            "uncached_input_tokens",
                            "tokens",
                            "tokens_used",
                        }:
                            structured[f"codex_cli_{key}"] = value
                    if structured:
                        usage = structured
                        usage_source = "codex_cli_json"
                        usage_exact = True
                if response_id is None:
                    for key in ("response_id", "id", "session_id"):
                        if isinstance(event.get(key), str):
                            response_id = event[key]
                            break
                if response_id is None:
                    for key in ("response_id", "id", "session_id"):
                        if isinstance(payload.get(key), str):
                            response_id = payload[key]
                            break
                if observed_model is None and isinstance(event.get("model"), str):
                    observed_model = event["model"]
                elif observed_model is None and isinstance(payload.get("model"), str):
                    observed_model = payload["model"]

        if usage_source is None and self.capture_tokens:
            for output_line in reversed(output_lines):
                match = re.search(r"tokens used\s*([\d,]+)", output_line, re.IGNORECASE)
                if match:
                    usage = {"codex_cli_reported_total": int(match.group(1).replace(",", ""))}
                    usage_source = "codex_cli_plaintext"
                    usage_exact = False
                    break
        return usage, usage_source, usage_exact, response_id, observed_model
