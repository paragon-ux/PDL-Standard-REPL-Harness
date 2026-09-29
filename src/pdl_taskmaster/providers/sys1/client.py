"""Sys1 Backend Client Abstraction.

Implements decoupled invocation of Sys1 single-pass classification endpoints.
Defaults to configuring via SYS1_* environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
import urllib.error
import urllib.request

from pdl_taskmaster.providers.sys1.schema import Sys1Request

logger = logging.getLogger(__name__)

DEFAULT_SYS1_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_SYS1_MODEL = os.environ.get("SYS1_MODEL", "typesafe/jev-1.13")


class Sys1Client:
    """Client for invoking Sys1 non-generative classification backends."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = (
                os.environ.get("SYS1_API_KEY")
                or os.environ.get("OPENROUTER_API_KEY")
                or ""
            )
        self.endpoint = (
            endpoint
            or os.environ.get("SYS1_ENDPOINT")
            or DEFAULT_SYS1_ENDPOINT
        )
        self.model = (
            model
            or os.environ.get("SYS1_MODEL")
            or DEFAULT_SYS1_MODEL
        )
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Check whether the client has an API key configured."""
        return bool(self.api_key.strip())

    def call(self, request: Sys1Request) -> tuple[dict[str, Any], float]:
        """Invoke the Sys1 backend with the given request.

        Returns:
            Tuple of (response_body_dict, duration_ms).
        """
        if not self.is_configured:
            raise ValueError("Sys1 API key is not configured (set SYS1_API_KEY or OPENROUTER_API_KEY)")

        payload = request.to_dict()
        if "model" not in payload or not payload["model"]:
            payload["model"] = self.model

        req_data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PDL-Taskmaster/Sys1Client",
        }

        req = urllib.request.Request(
            self.endpoint,
            data=req_data,
            headers=headers,
            method="POST",
        )

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                body = json.loads(resp.read().decode("utf-8"))
                return body, elapsed_ms
        except urllib.error.HTTPError as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            err_body = e.read().decode("utf-8", errors="replace")
            logger.warning("Sys1 backend returned HTTP %d: %s", e.code, err_body)
            raise RuntimeError(f"Sys1 HTTP {e.code}: {err_body}") from e
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("Sys1 backend request failed after %.1fms: %s", elapsed_ms, e)
            raise
