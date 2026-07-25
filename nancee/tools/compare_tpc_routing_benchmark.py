#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def percent_change(tpc: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return ((tpc - baseline) / baseline) * 100.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tpc", required=True)
    parser.add_argument("--no-tpc", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    tpc = json.loads(Path(args.tpc).read_text(encoding="utf-8"))
    no_tpc = json.loads(Path(args.no_tpc).read_text(encoding="utf-8"))

    rows = []
    for key, label in (
        ("foreground_first_token", "Foreground time to first token"),
        ("prompt_eval", "Prompt evaluation"),
        ("foreground_total", "Foreground request total"),
        ("route", "Router execution"),
    ):
        for statistic in ("mean", "median", "p95"):
            baseline = float(no_tpc[key][statistic])
            tpc_value = float(tpc[key][statistic])
            change = percent_change(tpc_value, baseline)
            rows.append((label, statistic, baseline, tpc_value, change))

    steady_tpc = tpc["steady_state"]
    steady_no_tpc = no_tpc["steady_state"]
    steady_first_change = percent_change(
        float(steady_tpc["foreground_first_token"]["median"]),
        float(steady_no_tpc["foreground_first_token"]["median"]),
    )
    steady_prompt_change = percent_change(
        float(steady_tpc["prompt_eval"]["median"]),
        float(steady_no_tpc["prompt_eval"]["median"]),
    )
    median_wait = float(tpc["tpc_wait"]["median"])

    if (
        steady_first_change <= -5.0
        and steady_prompt_change <= -5.0
        and median_wait < 0.10
    ):
        verdict = "TPC is helping steady-state foreground latency in this run."
    elif (
        steady_first_change >= 5.0
        or steady_prompt_change >= 5.0
        or median_wait >= 0.25
    ):
        verdict = "TPC is hurting or failing to hide its work in this run."
    else:
        verdict = "The result is too close to call; run the reverse order before deciding."

    lines = [
        "# NANCEE TPC + Routing Benchmark",
        "",
        f"**Verdict:** {verdict}",
        "",
        "Negative change means TPC was faster. Foreground metrics include any TPC wait.",
        "",
        "| Metric | Statistic | No TPC | TPC | Change |",
        "|---|---:|---:|---:|---:|",
    ]

    for label, statistic, baseline, tpc_value, change in rows:
        lines.append(
            f"| {label} | {statistic} | {baseline:.3f}s | {tpc_value:.3f}s | {change:+.1f}% |"
        )

    lines.extend(
        [
            "",
            "## Steady-state decision metrics (turns 2-30)",
            "",
            f"- Median first-token change: {steady_first_change:+.1f}%",
            f"- Median prompt-evaluation change: {steady_prompt_change:+.1f}%",
            "",
            "## TPC overhead",
            "",
            f"- Median foreground wait: {float(tpc['tpc_wait']['median']):.3f}s",
            f"- Maximum foreground wait: {float(tpc['tpc_wait']['max']):.3f}s",
            f"- Total foreground wait: {float(tpc['tpc_wait']['total']):.3f}s",
            f"- Total background prime work: {float(tpc['prime_work']['total']):.3f}s",
            "",
            "Background prime work is CPU/thermal cost even when fully hidden.",
            "Run the opposite order before removing or keeping TPC when the result is close.",
        ]
    )

    output = Path(args.output)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
