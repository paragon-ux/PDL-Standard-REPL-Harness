from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from providers.base import TransportError, WorkerResult

_JSON_ONLY_SUFFIX = (
    "\n\nReturn only a JSON object. Do not include markdown fences, commentary, or extra text."
)


DEFAULT_PROVIDER_PINNING: dict[str, Any] = {
    "order": ["Google", "Google AI Studio"],
    "allow_fallbacks": False,
}

DEFAULT_SAFETY_SETTINGS: list[dict[str, str]] = [
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
]


class ApiWorker:
    """LIVE SEMANTIC WORKER backed by a direct Responses-API HTTP call.

    This is a drop-in replacement for CodexWorker that talks straight to an
    OpenAI-compatible `/responses` endpoint (e.g. OpenRouter) instead of
    shelling out to `codex exec`. It sends exactly the same request.prompt
    every other worker receives -- no tool definitions, no sandbox, no
    agentic system prompt -- so the paid overhead is the actual projection
    content, not a coding-agent's scaffold.
    """

    def __init__(
        self,
        *,
        model: str = "google/gemini-2.5-flash",
        repo_root: str | Path,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key_env: str = "OPENROUTER_API_KEY",
        api_key_command: list[str] | None = None,
        timeout: float = 600.0,
        capture_tokens: bool = True,
        reasoning_effort: str | None = None,
        reasoning_by_operation: dict[str, str] | None = None,
        model_by_operation: dict[str, str] | None = None,
        reorder_keys_for_cache: bool = False,
        structured_output: bool = True,
        provider_pinning: dict[str, Any] | None = None,
        safety_settings: list[dict[str, str]] | None = None,
        on_progress: Any = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.capture_tokens = capture_tokens
        self.reasoning_effort = reasoning_effort
        self.reasoning_by_operation = dict(reasoning_by_operation or {})
        self.model_by_operation = dict(model_by_operation or {})
        self.reorder_keys_for_cache = reorder_keys_for_cache
        self.structured_output = structured_output
        self.provider_pinning = provider_pinning if provider_pinning is not None else dict(DEFAULT_PROVIDER_PINNING)
        self.safety_settings = safety_settings if safety_settings is not None else list(DEFAULT_SAFETY_SETTINGS)
        self.on_progress = on_progress
        self.worker_profile = "api"
        self.api_key_command = api_key_command or self._default_api_key_command(api_key_env)
        bootstrap_path = Path(repo_root) / "runtime" / "worker-bootstrap.txt"
        self._bootstrap = bootstrap_path.read_text(encoding="utf-8")
        self._bootstrap_prefix = self._bootstrap.rstrip() + "\n\n"

    @staticmethod
    def _default_api_key_command(env_name: str) -> list[str] | None:
        if os.environ.get(env_name):
            return None
        if sys.platform != "win32":
            return None
        # On Windows, fall back to reading Machine then User scope via PowerShell
        # to pick up variables defined outside the current process environment.
        script = (
            f"$v=[Environment]::GetEnvironmentVariable('{env_name}','Machine'); "
            f"if ([string]::IsNullOrWhiteSpace($v)) {{ $v=[Environment]::GetEnvironmentVariable('{env_name}','User') }}; "
            f"if ([string]::IsNullOrWhiteSpace($v)) {{ Write-Error '{env_name} not found in Machine or User environment'; exit 1 }}; "
            "[Console]::Out.Write($v)"
        )
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]

    def _resolve_api_key(self) -> str:
        if self.api_key_command is None:
            key = (os.environ.get(self.api_key_env) or "").strip()
            if not key:
                raise TransportError(f"could not resolve {self.api_key_env}: variable is unset or empty")
            return key
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

    def _model_for(self, operation: str | None) -> str:
        """Per-operation model wins over the global default."""
        if operation is not None and operation in self.model_by_operation:
            return self.model_by_operation[operation]
        return self.model

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

    @staticmethod
    def _sanitize_schema_for_grammar(schema: Any) -> Any:
        """Sanitize and flatten schema for grammar engines (Vertex, Venice, Outlines, vLLM).

        Flattens top-level oneOf unions into a single object schema with enum discriminators,
        converts 'const' to 'enum', and strips unsupported keywords like uniqueItems, minItems,
        minLength, anyOf, allOf, and $schema.
        """
        if not isinstance(schema, dict):
            return schema

        if "oneOf" in schema:
            merged_props: dict[str, Any] = {}
            required_discriminators: set[str] = set()
            for branch in schema["oneOf"]:
                if not isinstance(branch, dict):
                    continue
                props = branch.get("properties", {})
                for k, v in props.items():
                    if k not in merged_props:
                        merged_props[k] = dict(v) if isinstance(v, dict) else v
                    else:
                        existing = merged_props[k]
                        if isinstance(existing, dict) and isinstance(v, dict):
                            vals = set()
                            for item in (existing, v):
                                if "const" in item:
                                    vals.add(item["const"])
                                elif "enum" in item:
                                    vals.update(item["enum"])
                            if vals:
                                merged_props[k] = {"type": "string", "enum": sorted(list(vals))}
                reqs = branch.get("required", [])
                if not required_discriminators:
                    required_discriminators = set(reqs)
                else:
                    required_discriminators = required_discriminators.intersection(reqs)

            for k, v in list(merged_props.items()):
                if isinstance(v, dict):
                    cv = dict(v)
                    if "const" in cv:
                        cv["enum"] = [cv.pop("const")]
                        cv["type"] = "string"
                    for key_to_drop in ("anyOf", "allOf", "minItems", "maxItems", "uniqueItems", "minLength", "$schema"):
                        cv.pop(key_to_drop, None)
                    if "items" in cv and isinstance(cv["items"], dict):
                        cv_items = dict(cv["items"])
                        for key_to_drop in ("anyOf", "allOf", "minItems", "maxItems", "uniqueItems", "minLength", "$schema"):
                            cv_items.pop(key_to_drop, None)
                        cv["items"] = cv_items
                    merged_props[k] = cv

            res: dict[str, Any] = {
                "type": "object",
                "properties": merged_props,
                "additionalProperties": False,
            }
            if required_discriminators:
                res["required"] = sorted(list(required_discriminators))
            return res

        res = dict(schema)
        for key_to_drop in ("anyOf", "allOf", "minItems", "maxItems", "uniqueItems", "minLength", "$schema"):
            res.pop(key_to_drop, None)
        if "properties" in res and isinstance(res["properties"], dict):
            clean_props: dict[str, Any] = {}
            for k, v in res["properties"].items():
                cv = dict(v) if isinstance(v, dict) else v
                if isinstance(cv, dict):
                    if "const" in cv:
                        cv["enum"] = [cv.pop("const")]
                        cv["type"] = "string"
                    for key_to_drop in ("anyOf", "allOf", "minItems", "maxItems", "uniqueItems", "minLength", "$schema"):
                        cv.pop(key_to_drop, None)
                    if "items" in cv and isinstance(cv["items"], dict):
                        cv_items = dict(cv["items"])
                        for key_to_drop in ("anyOf", "allOf", "minItems", "maxItems", "uniqueItems", "minLength", "$schema"):
                            cv_items.pop(key_to_drop, None)
                        cv["items"] = cv_items
                clean_props[k] = cv
            res["properties"] = clean_props
        return res

    def call(self, request: Any) -> WorkerResult:
        instructions, input_text = self._split_prompt(request.prompt)
        if self.reorder_keys_for_cache:
            input_text = self._reorder_for_cache(input_text.lstrip())
        input_text = input_text.rstrip() + _JSON_ONLY_SUFFIX

        body: dict[str, Any] = {"model": self._model_for(getattr(request, "operation", None)), "input": input_text}
        if instructions:
            body["instructions"] = instructions
        effort = self._reasoning_for(getattr(request, "operation", None))
        if effort == "none":
            body["reasoning"] = {"enabled": False}
        elif effort:
            body["reasoning"] = {"effort": effort}

        if self.provider_pinning:
            body["provider"] = self.provider_pinning
        if self.safety_settings:
            body["safety_settings"] = self.safety_settings

        if self.structured_output:
            manifest = getattr(request, "manifest", None) or {}
            output_kind = manifest.get("output_kind", "json_object")
            schema = None
            projection = getattr(request, "projection", None)
            if projection is not None and isinstance(getattr(projection, "document", None), dict):
                schema = projection.document.get("output_schema")
            if not isinstance(schema, dict) and isinstance(manifest.get("output_schema"), dict):
                schema = manifest["output_schema"]
            elif not isinstance(schema, dict) and isinstance(manifest.get("output_schema"), str):
                schema_path = self.repo_root / manifest["output_schema"]
                if schema_path.is_file():
                    try:
                        schema = json.loads(schema_path.read_text(encoding="utf-8"))
                    except Exception:
                        schema = None
            if schema and isinstance(schema, dict):
                body["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": output_kind,
                        "schema": self._sanitize_schema_for_grammar(schema),
                    }
                }

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
        raw = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 502, 503, 504) and attempt < 4:
                    time.sleep(3.0 * (2 ** attempt))
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:2000]
                raise TransportError(f"api worker HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                if attempt < 4:
                    time.sleep(3.0 * (2 ** attempt))
                    continue
                raise TransportError(f"api worker transport error: {exc.reason}") from exc
            except (TimeoutError, socket.timeout) as exc:
                if attempt < 4:
                    time.sleep(3.0 * (2 ** attempt))
                    continue
                raise TransportError(f"api worker timed out after {self.timeout}s") from exc
        if raw is None:
            raise TransportError("api worker failed after retries")
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
