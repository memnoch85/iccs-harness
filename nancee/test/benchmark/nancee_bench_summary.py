#!/usr/bin/env python3
from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path


def values(pattern: str, text: str) -> list[float]:
    return [
        float(match)
        for match in re.findall(pattern, text)
    ]


def avg(items: list[float]) -> str:
    if not items:
        return "n/a"
    return f"{statistics.mean(items):.3f}s"


def maximum(items: list[float]) -> str:
    if not items:
        return "n/a"
    return f"{max(items):.3f}s"


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python3 nancee_bench_summary.py "
            "benchmark_logs/<file>.log",
            file=sys.stderr,
        )
        return 2

    path = Path(sys.argv[1])
    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    first_tokens = values(
        r"\[LLM FIRST TOKEN\]\s+([0-9.]+)s",
        text,
    )
    turn_totals = values(
        r"\[TURN DONE\]\s+total=([0-9.]+)s",
        text,
    )
    prompt_eval = values(
        r"\[OLLAMA DONE\].*?prompt_eval=([0-9.]+)s",
        text,
    )
    generation = values(
        r"\[OLLAMA DONE\].*?generation=([0-9.]+)s",
        text,
    )

    recall_hits = [
        int(value)
        for value in re.findall(
            r"\[MEMORY RECALL\]\s+query=.*?\shits=(\d+)",
            text,
        )
    ]

    guard_actions = re.findall(
        r"\[AUTHORITATIVE RESPONSE GUARD\]\s+"
        r"action=([A-Za-z0-9_]+)",
        text,
    )

    print(f"log: {path}")
    print(f"turns: {len(turn_totals)}")
    print(
        f"first_token_avg: {avg(first_tokens)} "
        f"max: {maximum(first_tokens)}"
    )
    print(
        f"prompt_eval_avg: {avg(prompt_eval)} "
        f"max: {maximum(prompt_eval)}"
    )
    print(
        f"generation_avg: {avg(generation)} "
        f"max: {maximum(generation)}"
    )
    print(
        f"turn_total_avg: {avg(turn_totals)} "
        f"max: {maximum(turn_totals)}"
    )
    print(
        "bridge_fires:",
        text.count("[LATENCY BRIDGE] fired"),
    )
    print(
        "length_cutoffs:",
        len(
            re.findall(
                r"\[OLLAMA DONE\]\s+reason=length",
                text,
            )
        ),
    )
    print(
        "memory_adds:",
        text.count("[MEMORY RAW ADD]"),
    )
    print(
        "memory_skips:",
        text.count("[MEMORY RAW SKIP]"),
    )
    print(
        "recall_queries:",
        len(recall_hits),
    )
    print(
        "recall_hits_total:",
        sum(recall_hits),
    )
    print(
        "recall_zero_hit_queries:",
        sum(1 for value in recall_hits if value == 0),
    )
    print(
        "perspective_repairs:",
        text.count("[MEMORY PERSPECTIVE REPAIR]"),
    )
    print(
        "grounding_fallbacks:",
        sum(
            action == "memory_grounding_fallback"
            for action in guard_actions
        ),
    )
    print(
        "profile_fallbacks:",
        sum(
            action == "profile_fallback"
            for action in guard_actions
        ),
    )
    print(
        "fact_miss_answers:",
        sum(
            action == "fact_miss_accepted"
            for action in guard_actions
        ),
    )

    if guard_actions:
        print(
            "guard_actions:",
            ", ".join(guard_actions),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
