"""Plan Soundness Gate (P0).

Deterministic harness-level validator that inspects Response Plans before transition
into execution for tasks requiring verified execution.

Conformant to ADR-0013 and Implementation Plan P0:
- Rejects deferral markers ("deferred to execution", "TBD", "left to execution").
- Rejects undisclosed single-pass/no-backtrack greedy scans proposed as decisive.
- Requires concrete commitment to code execution and complete search or disclosed heuristic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


_DEFERRAL_PATTERNS = re.compile(
    r"(?i)\b(?:(?:deferred|defer|postponed?|left|delegated?)\s+to\s+(?:the\s+)?execution(?:\s+stage|\s+phase)?|"
    r"TBD|to\s+be\s+determined(?:\s+at\s+execution)?|"
    r"(?:method|algorithm|approach|strategy)\s+(?:is\s+)?(?:undecided|left\s+open|determined\s+at\s+execution))\b"
)

_INCOMPLETE_HEURISTIC_PATTERNS = re.compile(
    r"(?i)\b(?:greedy\s+(?:scan|pass|selection|search|choice)|single\s+pass|without\s+backtracking|no\s+backtrack(?:ing)?)\b"
)

_HEURISTIC_DISCLOSURE_PATTERNS = re.compile(
    r"(?i)\b(?:not\s+proof\s+of\s+non-?existence|heuristic\s+failure\s+does\s+not\s+prove|incomplete\s+search|provisional|unverified)\b"
)

_CODE_EXECUTION_COMMITMENT_PATTERNS = re.compile(
    r"(?i)\b(?:execute|run|implement|script|python|code|program|solver|backtrack(?:ing)?|"
    r"exhaustive\s+search|depth-first|dfs|dynamic\s+programming|\bdp\b|sat\s+solver|"
    r"branch\s+and\s+bound|recurs(?:ive|ion)|combinatorial\s+search)\b"
)


_UNPRUNED_BRUTEFORCE_PATTERNS = re.compile(
    r"(?i)\b(?:unpruned\s+(?:permutations?|brute\s*force|dfs|search)|generate\s+all\s+permutations\b|"
    r"check\s+every\s+(?:single\s+)?permutation|naive\s+factorial\s+search)\b"
)


@dataclass(frozen=True)
class PlanSoundnessResult:
    valid: bool
    violations: list[str]

    @property
    def feedback(self) -> str:
        if self.valid:
            return ""
        return "Operational approach requirement: " + "; ".join(self.violations)


def validate_plan_soundness(
    plan_body: str,
    *,
    requires_verified_execution: bool = True,
) -> PlanSoundnessResult:
    """Validate Response Plan soundness before entering execution stage.

    Args:
        plan_body: The neutral plan body text.
        requires_verified_execution: Whether the current task was classified as requiring verified execution.

    Returns:
        PlanSoundnessResult with boolean valid status and any identified violations.
    """
    if not requires_verified_execution:
        return PlanSoundnessResult(valid=True, violations=[])

    violations: list[str] = []
    text = plan_body or ""

    # 1. Deferral check
    deferral_match = _DEFERRAL_PATTERNS.search(text)
    if deferral_match:
        matched = deferral_match.group(0).strip()
        violations.append(
            f"Plan contains deferral marker '{matched}' without a concrete algorithmic commitment. "
            "Specify the concrete search or solving method directly in the plan."
        )

    # 2. Incomplete heuristic without disclosure check
    heuristic_match = _INCOMPLETE_HEURISTIC_PATTERNS.search(text)
    if heuristic_match:
        has_disclosure = bool(_HEURISTIC_DISCLOSURE_PATTERNS.search(text))
        if not has_disclosure:
            matched = heuristic_match.group(0).strip()
            violations.append(
                f"Plan proposes an incomplete heuristic ('{matched}') without disclosing that failure "
                "to find a solution is not proof of non-existence. Commit to complete search (e.g. backtracking) "
                "or explicitly disclose heuristic limitations."
            )

    # 3. Unpruned brute force negative constraint check
    unpruned_match = _UNPRUNED_BRUTEFORCE_PATTERNS.search(text)
    if unpruned_match:
        matched = unpruned_match.group(0).strip()
        violations.append(
            f"Plan proposes an unpruned brute-force search ('{matched}'). "
            "Incorporate constraint pruning, MRV (minimum remaining values) heuristics, or early-exit bounds to prevent catastrophic factorial complexity."
        )

    # 4. Execution commitment check
    has_commitment = bool(_CODE_EXECUTION_COMMITMENT_PATTERNS.search(text))
    if not has_commitment:
        violations.append(
            "Plan for verified execution task does not commit to concrete code execution or a complete search algorithm. "
            "Commit to running a Python solver script or exhaustive search."
        )

    # 5. MRV / Constraint ordering check for combinatorial partitioning (ADR-0017)
    is_combinatorial = bool(
        re.search(
            r"(?i)\b(?:schur\s+triples?|partitioned?\b[^.\n]*\btriples?|exact\s+cover|subset\s*sum|triples\s+satisfying)\b",
            text,
        )
    )
    if is_combinatorial:
        has_mrv = bool(
            re.search(
                r"(?i)\b(?:mrv|minimum\s+remaining\s+values?|most\s+constrained|fewest\s+(?:candidate|overlap|choices?)|branch\s+on\s+element|constraint\s+(?:propagation|ordering|pruning)|overlap\s+ordering|forward\s+checking|degree\s+heuristic)\b",
                text,
            )
        )
        if not has_mrv:
            violations.append(
                "Plan for combinatorial partition/search must specify constraint-ordered branch selection or Minimum Remaining Values (MRV) heuristic (e.g. branch on elements with fewest candidate triples first) to prevent exponential search timeouts."
            )

    return PlanSoundnessResult(valid=len(violations) == 0, violations=violations)
