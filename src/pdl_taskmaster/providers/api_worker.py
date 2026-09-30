from __future__ import annotations

import http.client
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

from pdl_taskmaster.providers.base import TransportError, WorkerResult

_JSON_ONLY_SUFFIX = (
    "\n\nReturn only a JSON object. Do not include markdown fences, commentary, or extra text."
)


_SEMANTIC_READ_OPERATIONS = {"BOOTSTRAP_ANALYSIS", "INTERPRET_ACTIVATION"}

def _default_provider_order() -> list[str]:
    env_order = os.environ.get("OPENROUTER_PROVIDER_ORDER")
    if env_order:
        return [p.strip() for p in env_order.split(",") if p.strip()]
    primary = os.environ.get("OPENROUTER_PROVIDER", "Groq")
    fallbacks = ["Baseten", "Amazon Bedrock"]
    order = [primary]
    for fb in fallbacks:
        if fb.lower() != primary.lower():
            order.append(fb)
    return order


DEFAULT_PROVIDER_PINNING: dict[str, Any] = {
    "order": _default_provider_order(),
    "allow_fallbacks": True,
}

DEFAULT_SAFETY_SETTINGS: list[dict[str, str]] = [
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
]


class ApiWorker:
    """LIVE SEMANTIC WORKER backed by a direct Responses-API HTTP call.

    This is an API-backed alternative to CodexWorker that talks straight to an
    OpenAI-compatible `/responses` endpoint (e.g. OpenRouter) instead of
    shelling out to `codex exec`. It sends exactly the same request.prompt
    every other worker receives -- no tool definitions, no sandbox, no
    agentic system prompt -- so the paid overhead is the actual projection
    content, not a coding-agent's scaffold.
    """

    @staticmethod
    def _normalize_model_name(name: str) -> str:
        s = name.strip()
        if s.lower() in {"gpt-oss-120b", "openai/gpt-oss-120b"}:
            return "openai/gpt-oss-120b"
        return s

    def __init__(
        self,
        *,
        model: str = "openai/gpt-oss-120b",
        repo_root: str | Path,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key_env: str = "OPENROUTER_API_KEY",
        api_key_command: list[str] | None = None,
        timeout: float = 600.0,
        capture_tokens: bool = True,
        reasoning_effort: str | None = "low",
        reasoning_by_operation: dict[str, str] | None = None,
        model_by_operation: dict[str, str] | None = None,
        reorder_keys_for_cache: bool = False,
        structured_output: bool = True,
        provider_pinning: dict[str, Any] | None = None,
        safety_settings: list[dict[str, str]] | None = None,
        max_tokens: int = 4096,
        on_progress: Any = None,
    ):
        self.model = self._normalize_model_name(model)
        self.max_tokens = int(max_tokens)
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.capture_tokens = capture_tokens
        self.reasoning_effort = reasoning_effort
        if reasoning_by_operation:
            self.reasoning_by_operation = dict(reasoning_by_operation)
        else:
            from pdl_taskmaster.runtime.model_classification import get_proportional_reasoning_mapping
            mapping = get_proportional_reasoning_mapping(self.model)
            self.reasoning_by_operation = mapping if mapping else {}
        self.model_by_operation = dict(model_by_operation or {})
        self.reorder_keys_for_cache = reorder_keys_for_cache
        self.structured_output = structured_output
        self.provider_pinning = provider_pinning if provider_pinning is not None else dict(DEFAULT_PROVIDER_PINNING)
        self.safety_settings = safety_settings if safety_settings is not None else list(DEFAULT_SAFETY_SETTINGS)
        self.on_progress = on_progress
        self.worker_profile = "api"
        self.api_key_command = api_key_command or self._default_api_key_command(api_key_env)
        bootstrap_path = Path(__file__).resolve().parents[1] / "runtime" / "worker-bootstrap.txt"
        if not bootstrap_path.is_file():
            bootstrap_path = Path(repo_root) / "src" / "pdl_taskmaster" / "runtime" / "worker-bootstrap.txt"
        if not bootstrap_path.is_file():
            bootstrap_path = Path(repo_root) / "scripts" / "runtime" / "worker-bootstrap.txt"
        self.repo_root = Path(repo_root)
        self._bootstrap = bootstrap_path.read_text(encoding="utf-8")
        self._bootstrap_prefix = self._bootstrap.rstrip() + "\n\n"
        from pdl_taskmaster.providers.sys1.client import Sys1Client
        self.sys1_client = Sys1Client(api_key=self._resolve_api_key_safe())

    def _resolve_api_key_safe(self) -> str:
        try:
            return self._resolve_api_key()
        except Exception:
            return (os.environ.get("SYS1_API_KEY") or os.environ.get(self.api_key_env) or "").strip()

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

    def _reasoning_for(self, operation: str | None) -> str | int | None:
        """Per-operation effort wins over the global default; 'none' disables reasoning."""
        if operation is not None and operation in self.reasoning_by_operation:
            return self.reasoning_by_operation[operation]
        return self.reasoning_effort

    def _model_for(self, operation: str | None) -> str:
        """Per-operation model wins over the global default."""
        if operation is not None and operation in self.model_by_operation:
            return self._normalize_model_name(self.model_by_operation[operation])
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
        """Sanitize schema for strict grammar engines (Groq, Vertex, Venice, Outlines, vLLM).

        Inlines $defs/$ref pointers recursively, cleans unsupported keywords like
        $schema, title, description, minLength, converts 'const' to single-item 'enum',
        and enforces object constraints.
        """
        if not isinstance(schema, dict):
            return schema

        defs = schema.get("$defs", {}) or schema.get("definitions", {}) or {}

        def _clean_node(node: Any) -> Any:
            if not isinstance(node, dict):
                return node
            if "$ref" in node:
                ref_path = str(node["$ref"])
                if ref_path.startswith("#/$defs/") or ref_path.startswith("#/definitions/"):
                    def_name = ref_path.split("/")[-1]
                    if def_name in defs:
                        inlined = dict(defs[def_name])
                        for k, v in node.items():
                            if k != "$ref":
                                inlined[k] = v
                        return _clean_node(inlined)
            res: dict[str, Any] = {}
            for k, v in node.items():
                if k in (
                    "$defs",
                    "definitions",
                    "$schema",
                    "title",
                    "description",
                    "minLength",
                    "maxLength",
                    "minItems",
                    "maxItems",
                    "uniqueItems",
                ):
                    continue
                if isinstance(v, dict):
                    res[k] = _clean_node(v)
                elif isinstance(v, list):
                    res[k] = [_clean_node(item) for item in v]
                else:
                    res[k] = v
            if "const" in res:
                res["enum"] = [res.pop("const")]
                if "type" not in res:
                    res["type"] = "string"
            if "oneOf" in res and isinstance(res["oneOf"], list):
                res["anyOf"] = [_clean_node(b) for b in res.pop("oneOf")]
            if "anyOf" in res and isinstance(res["anyOf"], list):
                res["anyOf"] = [_clean_node(b) for b in res["anyOf"]]
            if "allOf" in res and isinstance(res["allOf"], list):
                res["allOf"] = [_clean_node(b) for b in res["allOf"]]
            if "properties" in res and isinstance(res["properties"], dict):
                if "required" not in res or not res["required"]:
                    res["required"] = list(res["properties"].keys())
                if "additionalProperties" not in res:
                    res["additionalProperties"] = False
            return res

        return _clean_node(schema)

    def _send_json_with_retries(self, req: urllib.request.Request) -> dict[str, Any]:
        """POST with exponential-backoff retries; returns the parsed response.

        Retries transient transport conditions: 429/5xx, URLError, timeouts.
        Non-retryable HTTP errors (4xx besides 429) raise immediately.
        """
        raw = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(raw)
                    err = parsed.get("error") if isinstance(parsed, dict) else None
                    if err and attempt < 4:
                        err_code = str(err.get("code") if isinstance(err, dict) else err).lower()
                        err_msg = str(err.get("message") if isinstance(err, dict) else "").lower()
                        if "server" in err_code or "rate" in err_code or "internal" in err_code or "timeout" in err_code or "failed to validate json" in err_msg:
                            delay = 0.5 * (2 ** attempt)
                            if self.on_progress is not None:
                                try:
                                    self.on_progress(
                                        f"upstream error ({err.get('code', 'error')}); retrying in {delay:.1f}s (attempt {attempt + 1}/5)..."
                                    )
                                except Exception:
                                    pass
                            time.sleep(delay)
                            continue
                    return parsed
                except json.JSONDecodeError:
                    break
            except urllib.error.HTTPError as exc:
                if (exc.code == 429 or 500 <= exc.code < 600) and attempt < 4:
                    delay = 0.5 * (2 ** attempt)
                    if exc.headers:
                        ra = exc.headers.get("Retry-After")
                        if ra:
                            try:
                                val = float(ra)
                                if 0.0 < val <= 10.0:
                                    delay = val
                            except (ValueError, TypeError):
                                pass
                    if self.on_progress is not None:
                        try:
                            self.on_progress(
                                f"HTTP {exc.code} received; retrying in {delay:.1f}s (attempt {attempt + 1}/5)..."
                            )
                        except Exception:
                            pass
                    time.sleep(delay)
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:2000]
                raise TransportError(f"api worker HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                if attempt < 4:
                    delay = 0.5 * (2 ** attempt)
                    if self.on_progress is not None:
                        try:
                            self.on_progress(
                                f"transport error: {exc.reason}; retrying in {delay:.1f}s (attempt {attempt + 1}/5)..."
                            )
                        except Exception:
                            pass
                    time.sleep(delay)
                    continue
                raise TransportError(f"api worker transport error: {exc.reason}") from exc
            except (
                TimeoutError,
                socket.timeout,
                ConnectionResetError,
                http.client.IncompleteRead,
                http.client.RemoteDisconnected,
                http.client.HTTPException,
            ) as exc:
                if attempt < 4:
                    delay = 0.5 * (2 ** attempt)
                    if self.on_progress is not None:
                        try:
                            self.on_progress(
                                f"connection error ({type(exc).__name__}: {exc}); retrying in {delay:.1f}s (attempt {attempt + 1}/5)..."
                            )
                        except Exception:
                            pass
                    time.sleep(delay)
                    continue
                raise TransportError(f"api worker connection failed after retries: {exc}") from exc
        if raw is None:
            raise TransportError("api worker failed after retries")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TransportError(f"api worker returned non-JSON response: {raw[:500]}") from exc

    def call(self, request: Any) -> WorkerResult:
        operation_name = getattr(request, "operation", None)

        # ADR-0017 / ADR-0020: Wire System 1 (Jev / ModernBERT) for fast classification, boundary enforcement, and review
        if operation_name == "INTERPRET_ACTIVATION":
            try:
                user_msg = ""
                proj = getattr(request, "projection", None)
                if proj and isinstance(getattr(proj, "document", None), dict):
                    user_msg = proj.document.get("operation_inputs", {}).get("RAW_USER_MESSAGE", "")
                if not user_msg:
                    try:
                        parsed_in = json.loads(request.prompt.split("\n\n", 1)[-1])
                        user_msg = parsed_in.get("operation_inputs", {}).get("RAW_USER_MESSAGE", "")
                    except Exception:
                        pass
                if user_msg:
                    from pdl_taskmaster.providers.sys1.recipes.activation_route import ActivationRouteRecipe
                    recipe = ActivationRouteRecipe()

                    # Fast-path deterministic scope & environment refusal (ADR-0020)
                    det_route, det_resp = recipe.classify_text_deterministic(user_msg)
                    if det_route:
                        wire_payload = {
                            "route": det_route,
                            "response": det_resp,
                        }
                        metadata = {
                            "worker": "sys1",
                            "model": "sys1-deterministic",
                            "observed_model": "sys1-deterministic",
                            "recipe": recipe.name,
                            "confidence": 1.0,
                            "latency_ms": 0.5,
                            "operation": operation_name,
                        }
                        return WorkerResult(json.dumps(wire_payload), metadata)

                    if not self.sys1_client.is_configured:
                        safe_k = self._resolve_api_key_safe()
                        if safe_k:
                            self.sys1_client.api_key = safe_k
                    if self.sys1_client.is_configured:
                        sys1_req = recipe.build_request({"request": user_msg})
                        resp_body, duration_ms = self.sys1_client.call(sys1_req)
                        result = recipe.parse_response(resp_body, duration_ms=duration_ms)
                        if result.passed_gating:
                            wire_payload = recipe.map_to_wire(result)
                            metadata = {
                                "worker": "sys1",
                                "model": self.sys1_client.model,
                                "observed_model": self.sys1_client.model,
                                "recipe": recipe.name,
                                "confidence": result.confidence,
                                "latency_ms": round(duration_ms, 3),
                                "operation": operation_name,
                            }
                            return WorkerResult(json.dumps(wire_payload), metadata)
            except Exception:
                pass

        elif operation_name == "BOOTSTRAP_ANALYSIS":
            try:
                raw_text = ""
                proj = getattr(request, "projection", None)
                if proj and isinstance(getattr(proj, "document", None), dict):
                    raw_text = proj.document.get("operation_inputs", {}).get("RAW_UNTRUSTED_CONTENT", "")
                if not raw_text:
                    try:
                        parsed_in = json.loads(request.prompt.split("\n\n", 1)[-1])
                        raw_text = parsed_in.get("operation_inputs", {}).get("RAW_UNTRUSTED_CONTENT", "")
                    except Exception:
                        pass
                if raw_text:
                    from pdl_taskmaster.providers.sys1.recipes.activation_route import ActivationRouteRecipe
                    det_route, det_resp = ActivationRouteRecipe.classify_text_deterministic(raw_text)
                    if det_route == "BLOCKED_BY_HIGHER_PRIORITY":
                        wire_payload = {
                            "kind": "BLOCKED_BY_HIGHER_PRIORITY",
                            "response": det_resp,
                        }
                        metadata = {
                            "worker": "sys1",
                            "model": "sys1-deterministic",
                            "observed_model": "sys1-deterministic",
                            "confidence": 1.0,
                            "latency_ms": 0.5,
                            "operation": operation_name,
                        }
                        return WorkerResult(json.dumps(wire_payload), metadata)
            except Exception:
                pass

        elif operation_name in ("INTERPRET_PROMPT_REVIEW", "INTERPRET_PLAN_REVIEW"):
            if not self.sys1_client.is_configured:
                safe_k = self._resolve_api_key_safe()
                if safe_k:
                    self.sys1_client.api_key = safe_k
            if self.sys1_client.is_configured:
                try:
                    proj = getattr(request, "projection", None)
                    doc = proj.document if proj and isinstance(getattr(proj, "document", None), dict) else {}
                    op_inputs = doc.get("operation_inputs", {})
                    subject_body = op_inputs.get("BOUND_REVIEW_SUBJECT_BODY", "")
                    user_msg = op_inputs.get("RAW_USER_REVIEW_MESSAGE", "")
                    artifact_kind = "plan" if operation_name == "INTERPRET_PLAN_REVIEW" else "prompt"

                    if not (subject_body and user_msg):
                        try:
                            parsed_in = json.loads(request.prompt.split("\n\n", 1)[-1])
                            op_inputs = parsed_in.get("operation_inputs", {})
                            subject_body = op_inputs.get("BOUND_REVIEW_SUBJECT_BODY", "")
                            user_msg = op_inputs.get("RAW_USER_REVIEW_MESSAGE", "")
                        except Exception:
                            pass

                    if subject_body and user_msg:
                        from pdl_taskmaster.providers.sys1.recipes.confirmation_match import ConfirmationMatchRecipe
                        from pdl_taskmaster.providers.sys1.recipes.review_facets import ReviewFacetsRecipe

                        conf_recipe = ConfirmationMatchRecipe()
                        conf_req = conf_recipe.build_request({"proposal": subject_body, "response": user_msg})
                        conf_body, duration_ms = self.sys1_client.call(conf_req)
                        conf_res = conf_recipe.parse_response(conf_body, duration_ms=duration_ms)

                        if conf_res.passed_gating and conf_res.verdict in ("agrees", "rejects"):
                            wire_payload = conf_recipe.map_to_wire(conf_res)
                            metadata = {
                                "worker": "sys1",
                                "model": self.sys1_client.model,
                                "observed_model": self.sys1_client.model,
                                "recipe": conf_recipe.name,
                                "confidence": conf_res.confidence,
                                "latency_ms": round(duration_ms, 3),
                                "operation": operation_name,
                            }
                            return WorkerResult(json.dumps(wire_payload), metadata)

                        # Evaluate multi-label review facets
                        facets_recipe = ReviewFacetsRecipe()
                        facets_req = facets_recipe.build_request({
                            "artifact_kind": artifact_kind,
                            "content": subject_body,
                            "feedback": user_msg,
                        })
                        facets_body, duration_ms2 = self.sys1_client.call(facets_req)
                        facets_res = facets_recipe.parse_response(facets_body, duration_ms=duration_ms2)
                        if facets_res.passed_gating:
                            wire_payload = facets_recipe.map_to_wire(facets_res)
                            metadata = {
                                "worker": "sys1",
                                "model": self.sys1_client.model,
                                "observed_model": self.sys1_client.model,
                                "recipe": facets_recipe.name,
                                "confidence": facets_res.confidence,
                                "latency_ms": round(duration_ms + duration_ms2, 3),
                                "operation": operation_name,
                            }
                            return WorkerResult(json.dumps(wire_payload), metadata)
                except Exception:
                    pass

        instructions, input_text = self._split_prompt(request.prompt)
        if self.reorder_keys_for_cache:
            input_text = self._reorder_for_cache(input_text.lstrip())
        input_text = input_text.rstrip() + _JSON_ONLY_SUFFIX

        body: dict[str, Any] = {
            "model": self._model_for(getattr(request, "operation", None)),
            "input": input_text,
            "max_tokens": self.max_tokens,
        }
        # ADR-0009 finding: schema enforcement on the semantic-read boundary
        # (BOOTSTRAP_ANALYSIS) degrades interpretation quality — a lazy
        # structured summary classifies substantive tasks as instruction-free,
        # losing the entire task upstream of every gate. Structured output is
        # for ops whose SHAPE is the contract (drafts, executions, reviews);
        # the semantic read must stay free-text.
        schema_enforced = self.structured_output and operation_name not in _SEMANTIC_READ_OPERATIONS

        extra_guidance = ""
        if operation_name in ("DRAFT_PROMPT", "REVISE_PROMPT"):
            extra_guidance = (
                "\n\nNORMATIVE GUIDELINES FOR PROMPT PSEUDOCODE (PDL-01 to PDL-08, PROMPT-01 to PROMPT-05):\n"
                "1. Express the prompt in clean Structured English using uppercase action verbs (PDL-01, PDL-04).\n"
                "   Example format:\n"
                "   PARTITION the input string into palindrome substrings where each character belongs to exactly one palindrome\n"
                "   MINIMIZE the number of cuts in the resulting partition\n"
                "   RETURN the minimum-cut partition and cut count\n"
                "2. Layout: Each distinct operation or requirement MUST appear on its own line (PDL-02).\n"
                "3. No Invented Field Schemas: DO NOT use fielded prefixes like 'TASK:', 'OUTPUT:', 'INPUT:', 'INCLUDE:', 'CONSTRAINTS:' (PDL-05). State each operation directly.\n"
                "4. Purpose-Complete Target: Prompt Pseudocode defines the substantive requirements to be solved upon execution (PROMPT-01). DO NOT insert internal meta-rules, drafting instructions, or negative execution prohibitions (PROMPT-02, PDL-08)."
            )
        elif operation_name in ("DRAFT_PLAN", "REVISE_PLAN"):
            extra_guidance = (
                "\n\nNORMATIVE GUIDELINES FOR RESPONSE PLAN PSEUDOCODE (PDL-01 to PDL-08, PLAN-01 to PLAN-10):\n"
                "1. Express the response plan in clean Structured English using uppercase action verbs (PDL-01, PDL-04).\n"
                "   Example format:\n"
                "   IDENTIFY all palindrome substrings within the target string\n"
                "   COMPUTE the minimum number of cuts required to partition the string\n"
                "   CONSTRUCT the partition corresponding to the minimum cut count\n"
                "   EMIT the resulting partition and count\n"
                "2. Layout: Each step MUST appear on its own line (PDL-02). DO NOT invent prefixes like 'STEP 1:', 'ACTION:', 'RESULT:' (PDL-05).\n"
                "3. Procedure to Deliverable: Specify the high-level procedural steps to execute and compute the concrete deliverable (PLAN-01, PLAN-02).\n"
                "4. Neutrality & No Placeholders: Do not leak substantive answers into the plan (PLAN-04), and NEVER insert placeholder steps or meta-prohibitions like 'insert placeholders without performing computation' (PLAN-10).\n"
                "5. Implementation Tasks: For prompts asking to implement, build, or write code, plan the software architecture and implementation steps (e.g. DEFINE, IMPLEMENT, RETURN, EMIT) to produce the complete deliverable. DO NOT plan interactive user input steps like 'RECEIVE input from user' or 'ASK for input' unless the user prompt explicitly requested an interactive dialogue.\n"
                "6. Algorithmic and Search Tasks: For tasks involving search, optimization, or partition, specify the algorithm, data structures, and termination conditions required to produce a valid deliverable.\n"
                "7. Analytical & Symbolic Tasks: For analytical reasoning, symbolic mathematics, word problems, or logic puzzles, plan the precise logical deduction or closed-form derivation directly. DO NOT plan backtracking search loops, numerical simulations, or fabricate concrete example values unless empirical code execution or concrete cases were explicitly requested.\n"
                "8. Environmental Bounds: The execution environment is completely offline with no network or internet access."
            )
        elif operation_name in ("EXECUTE", "DRAFT_EXECUTE", "DRAFT_EXECUTION", "EMIT_RESULT_IR"):
            extra_guidance = (
                "\n\nNORMATIVE GUIDELINES FOR EXECUTE & DRAFT_EXECUTE:\n"
                "- Environmental Bounds: The sandbox execution environment is strictly offline with NO network or internet access. Do not attempt HTTP requests or external socket connections.\n"
                "- Substantive Delivery: You MUST solve the problem, perform any required computation, and output the concrete final deliverable/result (e.g. concrete answers, solutions, code, or partitions), not an algorithmic description or meta-summary.\n"
                "- Autonomous Host Execution: DO NOT emit REQUEST_INPUT asking for execution runtime, computation results, or human execution. When code is requested or required, the host environment automatically executes the Python script in your deliverable 'body' in an isolated sandbox to certify the witness. Always emit a RESULT containing the complete deliverable and Result IR.\n"
                "- Analytical & Symbolic Tasks: For closed-form mathematical derivations, symbolic proofs, logic puzzles, or word problems with general variables (e.g. N, M, x), deliver the exact analytical reasoning, proof, or formula directly in clear prose or math. DO NOT invent concrete numerical sample values or construct backtracking search loops unless empirical computation was explicitly requested.\n"
                "- Implementation Tasks: When asked to implement, build, or write code for a function, module, scraper, or script (e.g. 'for a given input'), deliver the complete, self-contained implementation code (including a demonstration or sample input). DO NOT emit REQUEST_INPUT asking the user to provide sample data or runtime inputs.\n"
                "- Analysis and Specification Tasks: When the prompt provides text, requirements, or policy excerpts (whether inline, quoted, or fenced), analyze the provided text directly and emit RESULT. DO NOT emit REQUEST_INPUT asking for the text that was already provided in the prompt.\n"
                "- If SUPPLIED_EXECUTION_INPUT_SOURCE is provided, use it as the operative input data for your computation.\n"
                "- MANDATORY FOR VERIFIED / ALGORITHMIC TASKS: For tasks requiring verified algorithmic execution, the deliverable 'body' MUST contain the complete, executable Python solver script inside a ```python ... ``` block. Output the witness in the Result IR certifying substantive correctness, or print the concrete solution dictionary so the mechanical sandbox verifier can ingest it. Never output fabricated or guessed solutions in prose without code."
            )

        if instructions:
            body["instructions"] = instructions + extra_guidance
        elif extra_guidance:
            body["instructions"] = extra_guidance.strip()
        effort = self._reasoning_for(getattr(request, "operation", None))
        if effort == "none":
            body["reasoning"] = {"enabled": False}
        elif effort is not None:
            if isinstance(effort, int) or (isinstance(effort, str) and effort.isdigit()):
                body["reasoning"] = {"max_tokens": int(effort)}
            else:
                body["reasoning"] = {"effort": effort}

        if self.provider_pinning:
            body["provider"] = self.provider_pinning
        if self.safety_settings:
            body["safety_settings"] = self.safety_settings

        if schema_enforced:
            manifest = getattr(request, "manifest", None) or {}
            output_kind = manifest.get("output_kind", "json_object")
            from pdl_taskmaster.runtime.wire_payloads import get_operation_pydantic_schema
            schema = get_operation_pydantic_schema(operation_name)
            if not isinstance(schema, dict):
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
        data = self._send_json_with_retries(req)
        latency_ms = (time.perf_counter() - started) * 1000.0

        if self.on_progress is not None:
            try:
                self.on_progress(f"response received in {latency_ms:.0f}ms")
            except Exception:
                pass

        if data.get("error"):
            raise TransportError(f"api worker reported an error: {data['error']}")
        status = data.get("status")
        if status not in (None, "completed"):
            raise TransportError(f"api worker response status={status}: {data.get('incomplete_details')}")

        text = self._extract_output_text(data)
        if not text:
            # Empty output with status=completed is a stochastic upstream fault
            # (output tokens consumed, message dropped — observed on shared-pool
            # aggregators). It is a transport condition, not model behavior:
            # retry with the same exponential-backoff treatment as 429/5xx.
            for retry in range(3):
                time.sleep(0.5 * (2 ** retry))
                data = self._send_json_with_retries(req)
                text = self._extract_output_text(data)
                if text:
                    break
            if not text:
                raise TransportError("api worker returned no output_text content after empty-output retries")

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
