"""Control condition for protocol-comparison runs: one plain API call.

Sends the raw user message straight to an OpenAI-compatible /responses
endpoint with no protocol bootstrap, no standards, no tooling -- the same
model and endpoint the REPL api worker uses, minus everything the PDL
harness adds. Writes the response text, usage, and latency to a JSON file.

Auth mirrors providers/api_worker.py: environment variable first, with
PowerShell Machine->User scope lookup fallback on Windows.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


def resolve_api_key(env_name: str) -> str:
    key = (os.environ.get(env_name) or "").strip()
    if key:
        return key
    if sys.platform != "win32":
        raise SystemExit(f"could not resolve {env_name}: variable is not set in the environment")
    script = (
        f"$v=[Environment]::GetEnvironmentVariable('{env_name}','Machine'); "
        f"if ([string]::IsNullOrWhiteSpace($v)) {{ $v=[Environment]::GetEnvironmentVariable('{env_name}','User') }}; "
        f"if ([string]::IsNullOrWhiteSpace($v)) {{ Write-Error '{env_name} not found'; exit 1 }}; "
        "[Console]::Out.Write($v)"
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
    )
    key = (proc.stdout or "").strip()
    if proc.returncode != 0 or not key:
        raise SystemExit(f"could not resolve {env_name}")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description="Plain /responses call (control condition)")
    parser.add_argument("--message", required=True)
    parser.add_argument("--model", default="z-ai/glm-4.7")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    body = {"model": args.model, "input": args.message}
    req = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolve_api_key(args.api_key_env)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise SystemExit(f"HTTP {exc.code}: {detail}")
    latency_ms = (time.perf_counter() - started) * 1000.0

    text = "".join(
        part.get("text", "")
        for item in data.get("output") or []
        if item.get("type") == "message"
        for part in item.get("content") or []
        if part.get("type") == "output_text"
    ).strip()
    result = {
        "condition": "control-plain-api",
        "model": args.model,
        "observed_model": data.get("model"),
        "response_id": data.get("id"),
        "latency_ms": round(latency_ms, 3),
        "usage": data.get("usage"),
        "input_message": args.message,
        "output_text": text,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(f"CONTROL_RUN_OK {args.out} latency_ms={result['latency_ms']} usage={data.get('usage')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())