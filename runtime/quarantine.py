"""Quarantine compiler (protocol v2, semantic-bootstrap containment).

The data-plane compiler: verbatim evidence emitted by the semantic-read
(bootstrap) operation is compiled into sanitized compile-context inputs.

- `strip_evidence_sink`: removes balanced <<<EVIDENCE>>>/<<<END_EVIDENCE>>>
  spans (the ratified a' declared channel). Unbalanced markers are NEVER
  stripped (structural failure -- content stays scannable).
- `compile_bootstrap_output`: sanitizes the bootstrap analysis before it
  becomes a compile operation's context. Sink spans are stripped; verbatim
  quoted spans from the raw source are replaced with [REDACTED_IOC].

Declared policy, not output constraints: the model is told up front that sink
content is removed and literals must be redacted; failures to comply are
scored at the emitting stage. Compilation only stops downstream re-exposure.
"""
from __future__ import annotations

import re

EVIDENCE_SINK_OPEN = "<<<EVIDENCE>>>"
EVIDENCE_SINK_CLOSE = "<<<END_EVIDENCE>>>"

_QUOTED_SPAN = re.compile(r"(\"[^\"]{6,}\"|'[^']{6,}'|`[^`]{6,}`)")


def strip_evidence_sink(text: str) -> tuple[str, dict]:
    """Remove all balanced evidence-sink spans; return (stripped_text, meta).

    meta: sink_count (balanced pairs removed), structural_failure (True when an
    open marker has no close -- such text is left untouched so the literal
    remains scannable and the channeling failure is visible).
    """
    meta = {"sink_count": 0, "structural_failure": False}
    if not text or EVIDENCE_SINK_OPEN not in text:
        return text, meta
    out: list[str] = []
    i = 0
    while True:
        j = text.find(EVIDENCE_SINK_OPEN, i)
        if j < 0:
            out.append(text[i:])
            break
        k = text.find(EVIDENCE_SINK_CLOSE, j + len(EVIDENCE_SINK_OPEN))
        if k < 0:
            meta["structural_failure"] = True
            out.append(text[i:])
            break
        out.append(text[i:j])
        out.append("[EVIDENCE_REMOVED]")
        meta["sink_count"] += 1
        i = k + len(EVIDENCE_SINK_CLOSE)
    return "".join(out), meta


def compile_bootstrap_output(raw_source: str, analysis_text: str) -> tuple[str, dict]:
    """Sanitize a bootstrap analysis for use as a compile-operation input.

    1. Strip balanced evidence sinks (declared channel).
    2. Replace quoted spans whose content appears verbatim in the raw source
       with [REDACTED_IOC] (covers 'TRIPWIRE_X', "emit TRIPWIRE ...", `...`).
    3. Replace distinctive unquoted tokens (len>=8 containing a digit or
       underscore, or len>=20) that appear verbatim in the raw source --
       catches unquoted canary reproduction (measured in the v2 probe:
       DRIP-01/ENC-01 EXECUTE leaks routed via unquoted bootstrap echo).
    Returns (sanitized_text, meta{sinks, redactions}).
    """
    meta: dict = {"sinks": 0, "redactions": 0}
    text, sink_meta = strip_evidence_sink(analysis_text)
    meta["sinks"] = sink_meta["sink_count"]

    if not raw_source:
        return text, meta

    def _redact(m: re.Match) -> str:
        inner = m.group(1)[1:-1]
        if inner in raw_source:
            meta["redactions"] += 1
            return "[REDACTED_IOC]"
        return m.group(0)

    text = _QUOTED_SPAN.sub(_redact, text)

    def _redact_token(m: re.Match) -> str:
        tok = m.group(0)
        if tok in raw_source:
            meta["redactions"] += 1
            return "[REDACTED_IOC]"
        return tok

    text = re.sub(r"\b[A-Za-z0-9_]*(?:\d[\w]*)_[\w]*\b", _redact_token, text)  # underscore+digit style (tripwire-like)
    text = re.sub(r"\b[A-Za-z0-9_]{20,}\b", _redact_token, text)  # very long tokens
    return text, meta
