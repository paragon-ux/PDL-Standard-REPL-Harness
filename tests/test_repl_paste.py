from __future__ import annotations

import sys
from unittest.mock import patch
from pdl_taskmaster.host.repl import (
    PASTE_START,
    PASTE_END,
    _read_repl_input,
)
from pdl_taskmaster.providers.api_worker import ApiWorker


def test_normal_single_line_input():
    with patch("builtins.input", side_effect=["hello world"]):
        result = _read_repl_input()
        assert result == "hello world"


def test_single_line_bracketed_paste():
    # Single line bracketed paste should return immediately without confirmation prompt
    raw = f"{PASTE_START}single line paste{PASTE_END}"
    with patch("builtins.input", side_effect=[raw]):
        result = _read_repl_input()
        assert result == "single line paste"


def test_multiline_bracketed_paste_confirmed():
    # Multi-line paste: first input has PASTE_START + line 1, second has line 2 + PASTE_END.
    # Third input is empty Enter to confirm.
    inputs = [
        f"{PASTE_START}def foo():",
        f"    return 42{PASTE_END}",
        "",  # User presses Enter
    ]
    with patch("builtins.input", side_effect=inputs):
        result = _read_repl_input()
        assert result == "def foo():\n    return 42"


def test_multiline_bracketed_paste_with_prefix_suffix():
    inputs = [
        f"Solve this: {PASTE_START}first line",
        f"second line{PASTE_END} thanks",
        "",  # User presses Enter
    ]
    with patch("builtins.input", side_effect=inputs):
        result = _read_repl_input()
        assert result == "Solve this: first line\nsecond line thanks"


def test_multiline_bracketed_paste_cancelled():
    inputs = [
        f"{PASTE_START}line 1",
        f"line 2{PASTE_END}",
        "/cancel",  # User cancels
    ]
    with patch("builtins.input", side_effect=inputs):
        result = _read_repl_input()
        assert result == ""


def test_console_burst_paste_confirmed():
    inputs = [
        "step 1: do something",
        "step 2: verify something",
        "",  # User confirms with Enter
    ]
    with patch("sys.stdin.isatty", return_value=True), \
         patch("msvcrt.kbhit", side_effect=[True, False]), \
         patch("builtins.input", side_effect=inputs):
        result = _read_repl_input()
        assert result == "step 1: do something\nstep 2: verify something"


def test_console_burst_paste_discarded():
    inputs = [
        "step 1: do something",
        "step 2: verify something",
        "/cancel",
    ]
    with patch("sys.stdin.isatty", return_value=True), \
         patch("msvcrt.kbhit", side_effect=[True, False]), \
         patch("builtins.input", side_effect=inputs):
        result = _read_repl_input()
        assert result == ""


def test_triple_quote_multiline_input():
    inputs = [
        '"""',
        "line 1",
        "line 2",
        '"""',
    ]
    with patch("builtins.input", side_effect=inputs):
        result = _read_repl_input()
        assert result == "line 1\nline 2"


def test_backslash_continuation():
    inputs = [
        "line 1 \\",
        "line 2 \\",
        "line 3",
    ]
    with patch("builtins.input", side_effect=inputs):
        result = _read_repl_input()
        assert result == "line 1\nline 2\nline 3"


from pathlib import Path


def test_api_worker_max_tokens_default():
    worker = ApiWorker(repo_root=Path("."))
    assert worker.max_tokens == 4096


def test_api_worker_max_tokens_custom():
    worker = ApiWorker(repo_root=Path("."), max_tokens=8192)
    assert worker.max_tokens == 8192
