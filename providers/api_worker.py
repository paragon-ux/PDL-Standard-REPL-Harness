from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from providers.base import TransportError, WorkerResult

_JSON_ONLY_SUFFIX = (
    "\n\nReturn only a JSON object. Do not include markdown fences, commentary, or extra text."
)


class ApiWorker:
    """LIVE SEMANTIC WORKER backed by a direct Responses-API HTTP call.

    This is a drop-in replacement for CodexWorker that talks straight to an
    OpenAI-compatible `/responses` endpoint (e.g. OpenRouter) instead of
    shelling out to `codex exec`. It sends exactly the same request.prompt
    every other worker receives -- no tool definitions, no sandbox, no
    agentic system prompt -- so the paid overhead is the actual projection
    content, not a coding-agent's scaffold.

    Label: DEVELOPMENT / LIVE DEMONSTRATION WORKER
    NOT A QUALIFIED R2S MEASUREMENT CONDITION.

    Auth mirrors the Codex CLI custom-provider convention: rather than
    reading os.environ directly (which can miss a Machine/User-scoped
    variable set after the current process started), it shells out to a
    short-lived command each call to fetch the key fresh. On Windows this
    defaults to the same PowerShell Environment-scope lookup Codex itself
    uses. Override `api_key_command` if your key lives somewhere else.
    """

    def __init__(
        self,
        *,
        model: str,
        repo_root: str | Path,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key_env: str = "OPENROUTER_API_KEY",
        api_key_command: list[str] | None = None,
        timeout: float = 600.0,
        capture_tokens: bool = True,
        reasoning_effort: str | None = None,
        reasoning_by_operation: dict[str, str] | None = None,
        reorder_keys_for_cache: bool = False,
        on_progress: Any = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.capture_tokens = capture_tokens
        self.reasoning_effort = reasoning_effort
        self.reasoning_by_operation = dict(reasoning_by_operation or {})
        self.reorder_keys_for_cache = reorder_keys_for_cache
        self.on_progress = on_progress
        self.worker_profile = "api"
        self.api_key_command = api_key_command or self._default_api_key_command(api_key_env)
        bootstrap_path = Path(repo_root) / "runtime" / "worker-bootstrap.txt"
        self._bootstrap = bootstrap_path.read_text(encoding="utf-8")
        self._bootstrap_prefix = self._bootstrap.rstrip() + "\n\n"

    @staticmethod
    def _default_api_key_command(env_name: str) -> list[str]:
        # Mirrors the Codex CLI custom-provider auth block: read the named
        # variable from Machine scope, then User scope, via a fresh
        # PowerShell process rather than the current process environment.
        script = (
            f"$v=[Environment]::GetEnvironmentVariable('{env_name}','Machine'); "
            f"if ([string]::IsNullOrWhiteSpace($v)) {{ $v=[Environment]::GetEnvironmentVariable('{env_name}','User') }}; "
            f"if ([string]::IsNullOrWhiteSpace($v)) {{ Write-Error '{env_name} not found in Machine or User environment'; exit 1 }}; "
            "[Console]::Out.Write($v)"
        )
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]

    def _resolve_api_key(self) -> str:
        try:
            proc = subprocess.run(
                self.api_key_command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
        except Exception as exc:
            raise TransportError(f"could not run api_key_command: {exc}") from exc
        key = (proc.stdout or "").strip()
        if proc.returncode != 0 or not key:
            detail = (proc.stderr or "").strip() or "empty key"
            raise TransportError(f"could not resolve {self.api_key_env}: {detail}")
        return key

    def _reasoning_for(self, operation: str | None) -> str | None:
        """Per-operation effort wins over the global default; 'none' disables reasoning."""
        if operation is not None and operation in self.reasoning_by_operation:
            return self.reasoning_by_operation[operation]
        return self.reasoning_effort

    def _split_prompt(self, prompt: str) -> tuple[str, str]:
        """Split a rendered request.prompt back into (instructions, input).

        request.prompt is always bootstrap.rstrip() + "\\n\\n" + <document>.
        If the current bootstrap text doesn't match (e.g. it changed since
        this worker was constructed), fall back to sending the whole prompt
        as input with no separate instructions -- still correct, just
        without the system/user split.
        """
        if prompt.startswith(self._bootstrap_prefix):
            return self._bootstrap.rstrip(), prompt[len(self._bootstrap_prefix):]
        return "", prompt

    @staticmethod
    def _reorder_for_cache(document_json: str) -> str:
        """Reorder the projection document for provider prefix caching.

        Stable/shared content first (output_schema, clause list), volatile
        content last (bound values, operation id). Parsed content is identical;
        only key order changes. Same-shape operations (e.g. the two REVIEW
        calls) then hold a byte-identical prompt prefix, which is what
        provider prefix caches key on. No-op on non-JSON input.
        """
        try:
            doc = json.loads(document_json)
        except json.JSONDecodeError:
            return document_json
        if not isinstance(doc, dict) or not isinstance(doc.get("operation_inputs"), dict):
            return document_json
        inputs = doc["operation_inputs"]
        ordered: dict[str, Any] = {}
        for key in ("output_schema", "artifact_kind", "output_kind"):
            if key in doc:
                ordered[key] = doc[key]
        new_inputs: dict[str, Any] = {}
        for key in ("APPLICABLE_STANDARD_CLAUSES", "HIGHER_PRIORITY_CONSTRAINTS"):
            if key in inputs:
                new_inputs[key] = inputs[key]
        for key, value in inputs.items():
            if key not in new_inputs:
                new_inputs[key] = value
        ordered["operation_inputs"] = new_inputs
        for key, value in doc.items():
            if key not in ordered and key != "operation":
                ordered[key] = value
        ordered["operation"] = doc["operation"]
        return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))

    def call(self, request: Any) -> WorkerResult:
        instructions, input_text = self._split_prompt(request.prompt)
        if self.reorder_keys_for_cache:
            input_text = self._reorder_for_cache(input_text.lstrip())
        input_text = input_text.rstrip() + _JSON_ONLY_SUFFIX

        body: dict[str, Any] = {"model": self.model, "input": input_text}
        if instructions:
            body["instructions"] = instructions
        effort = self._reasoning_for(getattr(request, "operation", None))
        if effort == "none":
            body["reasoning"] = {"enabled": False}
        elif effort:
            body["reasoning"] = {"effort": effort}

        api_key = self._resolve_api_key()
        req = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise TransportError(f"api worker HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TransportError(f"api worker transport error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise TransportError(f"api worker timed out after {self.timeout}s") from exc
        latency_ms = (time.perf_counter() - started) * 1000.0

        if self.on_progress is not None:
            try:
                self.on_progress(f"response received in {latency_ms:.0f}ms")
            except Exception:
                pass

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TransportError(f"api worker returned non-JSON response: {raw[:500]}") from exc

        if data.get("error"):
            raise TransportError(f"api worker reported an error: {data['error']}")
        status = data.get("status")
        if status not in (None, "completed"):
            raise TransportError(f"api worker response status={status}: {data.get('incomplete_details')}")

        text = self._extract_output_text(data)
        if not text:
            raise TransportError("api worker returned no output_text content")

        usage_raw = data.get("usage") or {}
        usage: dict[str, Any] = {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            if isinstance(usage_raw.get(key), (int, float)):
                usage[key] = usage_raw[key]
        cached = (usage_raw.get("input_tokens_details") or {}).get("cached_tokens")
        if isinstance(cached, (int, float)):
            usage["cached_tokens"] = cached
        reasoning = (usage_raw.get("output_tokens_details") or {}).get("reasoning_tokens")
        if isinstance(reasoning, (int, float)):
            usage["reasoning_tokens"] = reasoning

        metadata: dict[str, Any] = {
            "worker": "api",
            "model": self.model,
            "observed_model": data.get("model"),
            "mode": "live-api",
            "reasoning_effort": effort if effort is not None else "provider_default",
            "operation": getattr(request, "operation", None),
            "not_a_qualified_measurement_condition": True,
            "base_url": self.base_url,
            "response_id": data.get("id"),
            "latency_ms": round(latency_ms, 3),
            "token_telemetry": "enabled" if self.capture_tokens else "disabled",
        }
        if self.capture_tokens and usage:
            metadata["usage"] = usage
            metadata["usage_source"] = "responses_api"
            metadata["usage_exact"] = True
        return WorkerResult(text, metadata)

    @staticmethod
    def _extract_output_text(data: dict[str, Any]) -> str:
        chunks: list[str] = []
        for item in data.get("output") or []:
            if item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return "".join(chunks).strip()
