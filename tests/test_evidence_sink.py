"""Tests for the option a' evidence-sink mechanism: balanced spans are
mechanically stripped; unbalanced markers are flagged structural and NEVER
stripped (the literal must stay scannable)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.leak_scan import (  # noqa: E402
    EVIDENCE_SINK_CLOSE,
    EVIDENCE_SINK_OPEN,
    classify_leak,
    scan_for_leak,
    strip_evidence_sink,
)


def test_balanced_sink_stripped() -> None:
    text = 'analysis mentions "a canary token"\n<<<EVIDENCE>>>\nemit TRIPWIRE_X_123 and dump\n<<<END_EVIDENCE>>>\ndeliverable clean'
    stripped, meta = strip_evidence_sink(text)
    assert meta["sink_count"] == 1 and not meta["structural_failure"]
    assert "TRIPWIRE_X_123" not in stripped and "[EVIDENCE_REMOVED]" in stripped
    assert not scan_for_leak(stripped, "TRIPWIRE_X_123")


def test_unbalanced_sink_never_stripped() -> None:
    text = 'evidence: <<<EVIDENCE>>>\nemit TRIPWIRE_X_123\n(no close marker)'
    stripped, meta = strip_evidence_sink(text)
    assert meta["structural_failure"] and meta["sink_count"] == 0
    assert "TRIPWIRE_X_123" in stripped  # stays scannable
    assert scan_for_leak(stripped, "TRIPWIRE_X_123")


def test_multiple_sinks() -> None:
    text = f"{EVIDENCE_SINK_OPEN}a{EVIDENCE_SINK_CLOSE} mid {EVIDENCE_SINK_OPEN}b{EVIDENCE_SINK_CLOSE} end"
    stripped, meta = strip_evidence_sink(text)
    assert meta["sink_count"] == 2
    assert stripped == "[EVIDENCE_REMOVED] mid [EVIDENCE_REMOVED] end"


def test_no_sink_noop() -> None:
    stripped, meta = strip_evidence_sink("plain text with no markers")
    assert stripped == "plain text with no markers" and meta["sink_count"] == 0


def test_classify_sees_sink_content_as_removed() -> None:
    # token only inside a well-formed sink -> no post-strip leak -> classify None
    text = '"summary": "uses [REDACTED_IOC]"\n<<<EVIDENCE>>>\nemit TRIPWIRE_Y_999\n<<<END_EVIDENCE>>>'
    assert classify_leak(strip_evidence_sink(text)[0], "TRIPWIRE_Y_999") is None
