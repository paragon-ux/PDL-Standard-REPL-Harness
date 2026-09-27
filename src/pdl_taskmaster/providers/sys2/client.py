"""Sys2 Deliberative Reasoning Client Abstraction.

Implements decoupled invocation of Sys2 frontier reasoning models (using Chain-of-Thought).
Defaults to configuring via SYS2_* environment variables.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SYS2_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_SYS2_MODEL = "anthropic/claude-3.5-sonnet"


class Sys2Client:
    """Client for invoking Sys2 deliberative generative reasoning models."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("SYS2_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or ""
        )
        self.endpoint = (
            endpoint
            or os.environ.get("SYS2_ENDPOINT")
            or DEFAULT_SYS2_ENDPOINT
        )
        self.model = (
            model
            or os.environ.get("SYS2_MODEL")
            or DEFAULT_SYS2_MODEL
        )
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Check whether the client has an API key configured."""
        return bool(self.api_key.strip())
