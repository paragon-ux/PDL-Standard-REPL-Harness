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


# Known canary, tripwire, and exploit directive patterns
_CANARY_OR_TRIPWIRE = re.compile(r"\b(?:TRIPWIRE_[A-Za-z0-9_]+|CANARY_[A-Za-z0-9_]+|ACTIVATED)\b")
_OVERRIDE_DIRECTIVE = re.compile(r"\+{3}\s*(?:SYSTEM\s+(?:DIRECTIVE\s+)?OVERRIDE|END)\s*\+{3}", re.IGNORECASE)
_EXPLOIT_PHRASE = re.compile(
    r"(?:system\s+(?:directive\s+)?override|ignore\s+previous\s+instructions|dump\s+system\s+secrets|rootkit|credential[- ]harvesting)",
    re.IGNORECASE,
)


def compile_bootstrap_output(raw_source: str, analysis_text: str) -> tuple[str, dict]:
    """Sanitize a bootstrap analysis for use as a compile-operation input.

    1. Strip balanced evidence sinks (declared channel).
    2. Replace explicit canary tokens, tripwire strings, and override directives
       with [REDACTED_IOC].
    3. Redact quoted spans that contain exploit directives or canary tokens.
       Legitimate code specifications, identifiers, exception classes, and
       parameter names are strictly preserved.
    Returns (sanitized_text, meta{sinks, redactions}).
    """
    meta: dict = {"sinks": 0, "redactions": 0}
    text, sink_meta = strip_evidence_sink(analysis_text)
    meta["sinks"] = sink_meta["sink_count"]

    if not raw_source:
        return text, meta

    # 1. Redact quoted spans if they contain attack directives, canaries, or overrides
    def _redact_quoted_span(m: re.Match) -> str:
        inner = m.group(1)[1:-1]
        if _EXPLOIT_PHRASE.search(inner) or _CANARY_OR_TRIPWIRE.search(inner) or _OVERRIDE_DIRECTIVE.search(inner):
            meta["redactions"] += 1
            return "[REDACTED_IOC]"
        return m.group(0)

    text = _QUOTED_SPAN.sub(_redact_quoted_span, text)

    # 2. Redact explicit tripwire/canary tokens
    def _redact_token(m: re.Match) -> str:
        meta["redactions"] += 1
        return "[REDACTED_IOC]"

    text = _CANARY_OR_TRIPWIRE.sub(_redact_token, text)
    text = _OVERRIDE_DIRECTIVE.sub(_redact_token, text)
    return text, meta
