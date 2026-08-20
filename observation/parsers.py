from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
import sys


def _candidate_path(candidate_repo: str | Path) -> str:
    value = str(Path(candidate_repo).resolve())
    if value not in sys.path:
        sys.path.insert(0, value)
    return value


def new_operation_bridge(candidate_repo: str | Path) -> Any:
    _candidate_path(candidate_repo)
    from runtime.operation_bridge import OperationBridge

    return OperationBridge(candidate_repo)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def operation_parsers() -> dict[str, str]:
    return {
        "INTERPRET_ACTIVATION": "parse_activation",
        "DRAFT_PROMPT": "parse_prompt_draft",
        "DRAFT_PLAN": "parse_plan_body",
        "REVISE_PROMPT": "parse_prompt_body",
        "REVISE_PLAN": "parse_plan_body",
        "INTERPRET_PROMPT_REVIEW": "parse_prompt_review",
        "INTERPRET_PLAN_REVIEW": "parse_plan_review",
        "INTERPRET_EXECUTION_INPUT": "parse_execution_input",
        "ANSWER_PROTOCOL_DISCUSSION": "parse_protocol_discussion",
        "EXECUTE": "parse_execution",
    }


def parse_operation_output(
    candidate_repo: str | Path,
    operation: str,
    raw_text: str,
) -> tuple[Any, str | None]:
    method = operation_parsers().get(operation)
    if method is None:
        return None, f"no_parser_for_operation:{operation}"
    try:
        bridge = new_operation_bridge(candidate_repo)
        parser = getattr(bridge, method)
        return _jsonable(parser(raw_text)), None
    except Exception as exc:  # observation must never alter the protocol result
        return None, f"{type(exc).__name__}: {exc}"
