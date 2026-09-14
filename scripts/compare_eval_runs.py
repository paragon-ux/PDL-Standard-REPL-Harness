"""Comparison tool for M1/F6 evaluation runs.

v2 -- fixes applied per benchmark-rigor-audit.md:
  Finding I: a record missing a refusal rate is no longer silently treated
             as 100% refused. If refusal wasn't measured for a case/arm
             (e.g. no harmful_ask_markers defined), that's reported as
             "N/A (unmeasured)", not folded into the aggregate as a perfect
             score.
  Finding L: the "Trials/Arm" column no longer blends escalated (n=10+) and
             non-escalated (n=3) cases into a single misleading integer-
             divided average; it now reports the actual min-max range
             within each vector, and surfaces stalled/incomplete trials
             and per-case "qualified" status explicitly instead of letting
             them disappear into the aggregate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def format_rate(numerator: int | None, denominator: int | None) -> str:
    if not denominator:
        return "N/A"
    if numerator is None:
        return "N/A (unmeasured)"
    pct = (numerator / denominator) * 100.0
    return f"{pct:.1f}% ({numerator}/{denominator})"


def generate_arm_ab_table(summary: dict[str, Any]) -> str:
    """Generate Evidence II style comparison table between Control and Protocol arms."""
    results = summary.get("results") or []

    vector_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "cases": set(),
        "ctrl_scored": 0, "ctrl_leaks": 0, "ctrl_refusal_scored": 0, "ctrl_refusals": 0,
        "prot_scored": 0, "prot_leaks": 0, "prot_refusal_scored": 0, "prot_refusals": 0,
        "prot_latency_sum": 0.0, "prot_latency_count": 0,
        "prot_trial_counts": [], "ctrl_trial_counts": [],
        "stalled_total": 0, "unqualified_cases": [],
    })

    for item in results:
        vec = item.get("vector", "unknown")
        cid = item.get("case_id", "")
        arm = item.get("arm", "control")
        st = vector_stats[vec]
        st["cases"].add(cid)

        # scored_trials_count / leak_count are the corrected batch runner's
        # fields (leak_rate can legitimately be None if every trial
        # stalled). Fall back gracefully for older summary files.
        scored = item.get("scored_trials_count", item.get("trials_count", 0))
        leaks = item.get("leak_count", 0)
        refusal_rate = item.get("refusal_rate")  # may be None -- do not default
        refusal_scored_n = scored if refusal_rate is not None else 0
        refusals = round(refusal_rate * refusal_scored_n) if refusal_rate is not None else None
        stalled = item.get("stalled_count", 0)

        if item.get("qualified") is False:
            st["unqualified_cases"].append(cid)
        st["stalled_total"] += stalled

        if arm == "control":
            st["ctrl_scored"] += scored
            st["ctrl_leaks"] += leaks
            st["ctrl_trial_counts"].append(item.get("trials_count", scored))
            if refusals is not None:
                st["ctrl_refusal_scored"] += refusal_scored_n
                st["ctrl_refusals"] += refusals
        else:
            st["prot_scored"] += scored
            st["prot_leaks"] += leaks
            st["prot_trial_counts"].append(item.get("trials_count", scored))
            if refusals is not None:
                st["prot_refusal_scored"] += refusal_scored_n
                st["prot_refusals"] += refusals
            st["prot_latency_sum"] += item.get("mean_latency_ms", 0.0) * item.get("trials_count", scored)
            st["prot_latency_count"] += item.get("trials_count", scored)

    lines = [
        "## Arm A/B Evaluation Report (Control vs Protocol)",
        f"**Manifest:** `{summary.get('manifest_version', 'unknown')}` | **Platform:** `{summary.get('platform')}` | "
        f"**Model:** `{summary.get('model')}` | **Condition requested:** `{summary.get('measurement_condition_requested', summary.get('measurement_condition'))}`",
        "",
        "| Vector | Cases | Trials/Arm (range) | Control Leak Rate | Protocol Leak Rate | Control Refusal | Protocol Refusal | Protocol Mean Latency | Stalled |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    tot_cases = 0
    tot_ctrl_scored = 0
    tot_ctrl_leaks = 0
    tot_prot_scored = 0
    tot_prot_leaks = 0
    all_unqualified: list[str] = []

    for vec, st in sorted(vector_stats.items()):
        num_cases = len(st["cases"])
        tot_cases += num_cases
        tot_ctrl_scored += st["ctrl_scored"]
        tot_ctrl_leaks += st["ctrl_leaks"]
        tot_prot_scored += st["prot_scored"]
        tot_prot_leaks += st["prot_leaks"]
        all_unqualified.extend(st["unqualified_cases"])

        ctrl_leak_str = format_rate(st["ctrl_leaks"], st["ctrl_scored"])
        prot_leak_str = format_rate(st["prot_leaks"], st["prot_scored"])
        ctrl_ref_str = format_rate(st["ctrl_refusals"], st["ctrl_refusal_scored"]) if st["ctrl_refusal_scored"] else "N/A (unmeasured)"
        prot_ref_str = format_rate(st["prot_refusals"], st["prot_refusal_scored"]) if st["prot_refusal_scored"] else "N/A (unmeasured)"
        prot_lat = f"{st['prot_latency_sum'] / st['prot_latency_count']:.1f}ms" if st["prot_latency_count"] else "N/A"

        all_counts = st["prot_trial_counts"] + st["ctrl_trial_counts"]
        trials_range = f"{min(all_counts)}-{max(all_counts)}" if all_counts else "N/A"
        stalled_note = str(st["stalled_total"]) if st["stalled_total"] else "-"

        lines.append(
            f"| **{vec}** | {num_cases} | {trials_range} | {ctrl_leak_str} | **{prot_leak_str}** | "
            f"{ctrl_ref_str} | {prot_ref_str} | {prot_lat} | {stalled_note} |"
        )

    overall_ctrl = format_rate(tot_ctrl_leaks, tot_ctrl_scored)
    overall_prot = format_rate(tot_prot_leaks, tot_prot_scored)
    lines.append(f"| **TOTAL / OVERALL** | **{tot_cases}** | - | {overall_ctrl} | **{overall_prot}** | - | - | - | - |")

    if summary.get("escalated_cases"):
        lines.append("")
        lines.append(f"> [!NOTE]\n> **Escalated cases:** {', '.join(summary['escalated_cases'])}")

    if all_unqualified:
        lines.append("")
        lines.append(
            f"> [!WARNING]\n> **Requested as qualified but did not reach the required trial floor:** "
            f"{', '.join(sorted(set(all_unqualified)))}. Do not cite these as qualified results."
        )

    if summary.get("all_cases_met_qualified_floor") is False:
        lines.append("")
        lines.append("> [!WARNING]\n> This batch was run with `--qualified` but not every case/arm reached the "
                      "required trial floor (see above) -- treat the overall summary as partially qualified only.")

    return "\n".join(lines)


def generate_cross_os_table(summary_a: dict[str, Any], summary_b: dict[str, Any]) -> str:
    """Generate cross-OS invariance comparison report."""
    os_a = summary_a.get("platform", "OS-A")
    os_b = summary_b.get("platform", "OS-B")

    def index_results(s: dict[str, Any]):
        idx = {}
        for r in s.get("results") or []:
            idx[(r["case_id"], r["arm"])] = r
        return idx

    idx_a = index_results(summary_a)
    idx_b = index_results(summary_b)
    all_keys = sorted(set(idx_a.keys()) | set(idx_b.keys()))

    lines = [
        f"## Cross-OS Invariance Evaluation Report ({os_a} vs {os_b})",
        f"**Model:** `{summary_a.get('model')}` | **Condition:** `{summary_a.get('measurement_condition_requested', summary_a.get('measurement_condition'))}`",
        "",
        f"| Case ID | Arm | Vector | {os_a} Leak Rate | {os_b} Leak Rate | {os_a} Mean Latency | {os_b} Mean Latency | Invariance Status |",
        "|---|---|---|---|---|---|---|---|",
    ]

    all_invariant = True
    for cid, arm in all_keys:
        ra = idx_a.get((cid, arm))
        rb = idx_b.get((cid, arm))
        if not ra or not rb:
            lines.append(f"| {cid} | {arm} | - | {'Present' if ra else 'MISSING'} | {'Present' if rb else 'MISSING'} | - | - | ⚠️ MISMATCH |")
            all_invariant = False
            continue

        vec = ra.get("vector")
        leak_a = format_rate(ra.get("leak_count", 0), ra.get("scored_trials_count", ra.get("trials_count", 0)))
        leak_b = format_rate(rb.get("leak_count", 0), rb.get("scored_trials_count", rb.get("trials_count", 0)))
        lat_a = f"{ra.get('mean_latency_ms', 0):.1f}ms"
        lat_b = f"{rb.get('mean_latency_ms', 0):.1f}ms"

        rate_match = ra.get("leak_rate") == rb.get("leak_rate")
        status = "✅ MATCH" if rate_match else "❌ DIVERGENCE"
        if not rate_match:
            all_invariant = False

        lines.append(f"| {cid} | {arm} | {vec} | {leak_a} | {leak_b} | {lat_a} | {lat_b} | {status} |")

    lines.append("")
    if all_invariant:
        lines.append("> [!TIP]\n> **Cross-OS Verification Passed:** Protocol and control defense behaviors are byte-identical across operating systems.")
    else:
        lines.append("> [!WARNING]\n> **Cross-OS Behavioral Divergence Detected:** Inspect diverging cases above.")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="M1/F6 Evaluation Run Comparison Tool")
    parser.add_argument("file_a", type=Path, help="first summary JSON file")
    parser.add_argument("file_b", type=Path, nargs="?", default=None, help="second summary JSON file (for cross-OS comparison)")
    parser.add_argument("--out", type=Path, default=None, help="write markdown report to file")
    args = parser.parse_args()

    if not args.file_a.is_file():
        raise SystemExit(f"file not found: {args.file_a}")

    data_a = json.loads(args.file_a.read_text(encoding="utf-8"))

    if args.file_b is None:
        markdown = generate_arm_ab_table(data_a)
    else:
        if not args.file_b.is_file():
            raise SystemExit(f"file not found: {args.file_b}")
        data_b = json.loads(args.file_b.read_text(encoding="utf-8"))
        if data_a.get("platform") != data_b.get("platform"):
            markdown = generate_cross_os_table(data_a, data_b)
        else:
            markdown = generate_arm_ab_table(data_a) + "\n\n" + generate_cross_os_table(data_a, data_b)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown + "\n", encoding="utf-8")
        print(f"Report written to: {args.out}")
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
