"""Deterministic Verifier for Sum Triples / Schur Triples Partition Problems (P2).

Validates that:
1. Every triple [a, b, c] satisfies the sum property (x + y == z).
2. All triples are disjoint (no duplicate values across triples).
3. All required input elements are partitioned completely without extras or omissions.
4. For negative claims, search_exhausted is strictly True.
"""

from __future__ import annotations

from typing import Any, Sequence

from pdl_taskmaster.verification.checkers.base import BaseChecker, VerificationVerdict


class PartitionSumTriplesChecker(BaseChecker):
    """Deterministic mechanical checker for integer partition into sum triples."""

    @property
    def name(self) -> str:
        return "partition_sum_triples"

    def check(
        self,
        witness: dict[str, Any] | Any,
        constraints: dict[str, Any],
        *,
        body: str | None = None,
    ) -> VerificationVerdict:
        if witness is None:
            if body:
                extracted = self._extract_triples_from_text(body)
                if extracted:
                    witness = {
                        "polarity": "positive",
                        "evidence": {"path": "execution://body"},
                        "data": {"triples": extracted},
                    }
            if witness is None:
                return VerificationVerdict(
                    valid=False,
                    diagnostic="Missing witness in Result IR for sum-triples partition task.",
                )

        # Convert Pydantic model to dict if needed
        if hasattr(witness, "model_dump"):
            w_dict = witness.model_dump()
        elif isinstance(witness, dict):
            w_dict = witness
        else:
            return VerificationVerdict(
                valid=False,
                diagnostic=f"Witness must be an object, got {type(witness).__name__}.",
            )

        polarity = w_dict.get("polarity")
        if polarity == "positive":
            return self._check_positive(w_dict, constraints)
        elif polarity == "negative":
            return self._check_negative(w_dict, constraints)
        else:
            return VerificationVerdict(
                valid=False,
                diagnostic=f"Unknown witness polarity: {polarity!r}; must be 'positive' or 'negative'.",
            )

    def _check_positive(
        self,
        witness: dict[str, Any],
        constraints: dict[str, Any],
    ) -> VerificationVerdict:
        data = witness.get("data")
        if not isinstance(data, dict):
            return VerificationVerdict(
                valid=False,
                diagnostic="Positive witness must contain 'data' dictionary.",
            )

        triples = data.get("triples")
        if not isinstance(triples, list):
            return VerificationVerdict(
                valid=False,
                diagnostic="Positive witness data must contain a 'triples' list.",
            )

        expected_count = constraints.get("expected_triples_count")
        if expected_count is not None and len(triples) != expected_count:
            return VerificationVerdict(
                valid=False,
                diagnostic=f"Expected {expected_count} triples, but got {len(triples)}.",
            )

        all_elements: list[int] = []
        for i, triple in enumerate(triples, 1):
            if not isinstance(triple, (list, tuple)) or len(triple) != 3:
                return VerificationVerdict(
                    valid=False,
                    diagnostic=f"Triple {i} {triple!r} is not a valid 3-element list.",
                )
            try:
                nums = [int(x) for x in triple]
            except (ValueError, TypeError):
                return VerificationVerdict(
                    valid=False,
                    diagnostic=f"Triple {i} {triple!r} contains non-integer values.",
                )

            # Check sum constraint: smallest two must sum to largest
            nums_sorted = sorted(nums)
            if nums_sorted[0] + nums_sorted[1] != nums_sorted[2]:
                return VerificationVerdict(
                    valid=False,
                    diagnostic=(
                        f"Triple {i} ({nums[0]}, {nums[1]}, {nums[2]}) violates sum constraint: "
                        f"{nums_sorted[0]} + {nums_sorted[1]} != {nums_sorted[2]}."
                    ),
                )
            all_elements.extend(nums)

        # Check disjointness / uniqueness across triples
        if len(all_elements) != len(set(all_elements)):
            # Find duplicate elements
            seen = set()
            duplicates = set()
            for x in all_elements:
                if x in seen:
                    duplicates.add(x)
                seen.add(x)
            return VerificationVerdict(
                valid=False,
                diagnostic=f"Triples are not disjoint; duplicate elements found: {sorted(duplicates)}.",
            )

        # Check coverage against expected input elements if provided
        input_elements = constraints.get("input_elements") or constraints.get("integers")
        if input_elements is None:
            p_text = constraints.get("prompt_body") or constraints.get("user_message") or ""
            if p_text:
                import re
                for line in p_text.splitlines():
                    nums_in_line = re.findall(r"\b\d+\b", line)
                    if len(nums_in_line) >= 9:
                        input_elements = [int(x) for x in nums_in_line]
                        break
        if input_elements is not None:
            expected_set = set(int(x) for x in input_elements)
            actual_set = set(all_elements)
            missing = expected_set - actual_set
            extra = actual_set - expected_set

            if missing:
                return VerificationVerdict(
                    valid=False,
                    diagnostic=f"Partition misses required elements: {sorted(missing)}.",
                )
            if extra:
                return VerificationVerdict(
                    valid=False,
                    diagnostic=f"Partition includes unexpected elements: {sorted(extra)}.",
                )

        return VerificationVerdict(
            valid=True,
            diagnostic=None,
            details={"triples_verified": len(triples), "elements_partitioned": len(all_elements)},
        )

    def _check_negative(
        self,
        witness: dict[str, Any],
        constraints: dict[str, Any],
    ) -> VerificationVerdict:
        search_exhausted = witness.get("search_exhausted")
        if search_exhausted is not True:
            return VerificationVerdict(
                valid=False,
                diagnostic="Negative witness search_exhausted must be True to prove non-existence.",
            )

        nodes_explored = witness.get("nodes_explored")
        if not isinstance(nodes_explored, int) or nodes_explored < 0:
            return VerificationVerdict(
                valid=False,
                diagnostic="Negative witness must include non-negative integer 'nodes_explored'.",
            )

        if nodes_explored <= 1 and (constraints.get("prompt_body") or constraints.get("user_message")):
            return VerificationVerdict(
                valid=False,
                diagnostic="Negative witness search_exhausted is invalid: exploring <= 1 nodes cannot prove non-existence for a non-trivial integer partition problem without mathematical impossibility proof.",
            )

        method = witness.get("method")
        if not isinstance(method, str) or not method.strip():
            return VerificationVerdict(
                valid=False,
                diagnostic="Negative witness must include non-empty 'method' string.",
            )

        return VerificationVerdict(
            valid=True,
            diagnostic=None,
            details={
                "search_exhausted": True,
                "nodes_explored": nodes_explored,
                "method": method,
            },
        )

    @staticmethod
    def _extract_triples_from_text(text: str) -> list[list[int]] | None:
        import re
        pattern = r"[\(\[]\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*[\)\]]"
        matches = re.findall(pattern, text)
        if matches and len(matches) >= 3:
            return [[int(a), int(b), int(c)] for a, b, c in matches]
        return None

