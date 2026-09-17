"""Quarantine sanitizer (protocol v2, semantic-bootstrap containment).

The data-plane sanitizer: verbatim content emitted by the semantic-read
(bootstrap) operation is sanitized before it becomes a compile operation's
context.

- `compile_bootstrap_output`: sanitizes the bootstrap analysis before it
  becomes a compile operation's context. Explicit canary tokens, tripwire
  strings, override directives, and quoted spans carrying them are replaced
  with [REDACTED_IOC]. Legitimate code specifications, identifiers, exception
  classes, and parameter names are strictly preserved.

The retired in-band evidence-sink delimiters (`<<<EVIDENCE>>>` /
`<<<END_EVIDENCE>>>`) and their mechanical strip were permanently removed per
Decision D24 / TRD-0002: containment is out-of-band schema field isolation
(`task_summary` vs `risk_notes`), never in-band delimiter fences.
"""
from __future__ import annotations

import re

# Known canary, tripwire, and exploit directive patterns
_CANARY_OR_TRIPWIRE = re.compile(
    r"\b(?:TRIPWIRE_[A-Za-z0-9_]+|CANARY_[A-Za-z0-9_]+|PWNED_[A-Za-z0-9_]+|ACTIVATED|ROOTKIT-[A-Za-z0-9_]+)\b"
)
_OVERRIDE_DIRECTIVE = re.compile(r"\+{3}\s*(?:SYSTEM\s+(?:DIRECTIVE\s+)?OVERRIDE|END)\s*\+{3}", re.IGNORECASE)

# D29 generalized opaque-identifier shapes: canaries need not carry a
# recognizable prefix (UUID / long-hex canaries measurably reached the
# deliverable on the primary tier -- runs/canary_shape_probe). These
# apply ONLY to the sanitized summary surface, where an untrusted literal
# of digest length or UUID shape has no legitimate role; digest
# verification belongs in code, which this sanitizer never touches
# (execution-stage output is out of scope). Deliberate policy: >=32 hex
# chars includes SHA-256-length digests on this surface -- refer to them
# by role, not verbatim.
_UUID_SHAPE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_LONG_HEX_RUN = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_EXPLOIT_PHRASE = re.compile(
    r"(?:system\s+(?:directive\s+)?override|ignore\s+previous\s+instructions|dump\s+system\s+secrets|rootkit|credential[- ]harvesting)",
    re.IGNORECASE,
)
_QUOTED_SPAN = re.compile(r"(\"[^\"]{6,}\"|'[^']{6,}'|`[^`]{6,}`)")


def compile_bootstrap_output(raw_source: str, analysis_text: str) -> tuple[str, dict]:
    """Sanitize a bootstrap analysis for use as a compile-operation input.

    1. Replace explicit canary tokens, tripwire strings, and override directives
       with [REDACTED_IOC].
    2. Redact quoted spans that contain exploit directives or canary tokens.
       Legitimate code specifications, identifiers, exception classes, and
       parameter names are strictly preserved.
    Returns (sanitized_text, meta{redactions}).
    """
    meta: dict = {"redactions": 0}
    if not analysis_text:
        return "", meta

    text = analysis_text
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

    # 3. D29 generalized-shape redaction (prefix-independent canaries)
    def _redact_generalized(m: re.Match) -> str:
        meta["redactions_generalized"] = meta.get("redactions_generalized", 0) + 1
        return "[REDACTED_IOC]"

    text = _UUID_SHAPE.sub(_redact_generalized, text)
    text = _LONG_HEX_RUN.sub(_redact_generalized, text)
    return text, meta
