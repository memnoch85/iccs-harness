#!/usr/bin/env python3
"""
Benchmark NANCEE short-term-memory consolidation.

Compares:
1. Baseline unbounded sequential history
2. RLM-inspired block consolidation

Uses the existing NANCEE warmup command unchanged.
Skips ASR and TTS.
Writes CSV results to memory_benchmark_results/.

The benchmark reports cold cache transitions separately from normal
steady-state latency. Use --warmup skip only immediately after manually
running /usr/local/bin/nancee-ollama-warmup for the same model.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import statistics
import subprocess
import time
import urllib.error
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import (
    LLM_MODEL,
    MEMORY_CONSOLIDATE_CHARACTERS,
    MEMORY_CONSOLIDATE_TURNS,
    MEMORY_KEEP_RECENT_TURNS,
    OLLAMA_WARMUP_COMMAND,
    OLLAMA_WARMUP_TIMEOUT,
)
from memory_consolidator import consolidate_memory
from ollama_runtime import stream_ollama_response
from short_term_memory import ShortTermMemory

TURN_PROMPTS = [
    "My name is Anders. Remember that. Reply briefly.",
    "We are testing memory during an ordinary drive. Reply briefly.",
    "My daughter is named Copeland. Remember that. Reply briefly.",
    "We discussed taking a quiet road trip. Reply briefly.",
    "My favorite road-trip snack is mango slices. Remember that. Reply briefly.",
    "We talked about listening to music in the car. Reply briefly.",
    "We discussed going for a hike while waiting. Reply briefly.",
    "The exact test code is ORBIT-731. Remember it exactly. Reply briefly.",
    "This is the ninth benchmark turn. Reply briefly.",
    "We are continuing after the first memory checkpoint. Reply briefly.",
    "We discussed a normal afternoon drive. Reply briefly.",
    "Today's destination is the ice skating rink. Remember that. Reply briefly.",
    "We talked about parking near the entrance. Reply briefly.",
    "This is another ordinary filler turn. Reply briefly.",
    "This is the final ordinary benchmark turn. Reply briefly.",
]

RECALL_PROBES = [
    ("user_name", "What is my name?", "Anders"),
    ("daughter_name", "What is my daughter's name?", "Copeland"),
    ("road_trip_snack", "What is my favorite road-trip snack?", "mango"),
    ("test_code", "What exact test code did I ask you to remember?", "ORBIT-731"),
    ("destination", "What is today's destination?", "ice skating rink"),
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("baseline", "consolidated", "both"),
        default="both",
    )
    parser.add_argument(
        "--output-dir",
        default="memory_benchmark_results",
    )
    parser.add_argument(
        "--warmup",
        choices=("always", "skip"),
        default="always",
        help=(
            "Run NANCEE's existing warmup before each scenario, or skip it "
            "when you have just run the warmup manually. Default: always"
        ),
    )
    return parser.parse_args()


def run_existing_warmup():
    started = time.perf_counter()

    print(
        f"[BENCHMARK] Running existing warmup: {OLLAMA_WARMUP_COMMAND} {LLM_MODEL}",
        flush=True,
    )

    result = subprocess.run(
        [OLLAMA_WARMUP_COMMAND, LLM_MODEL],
        check=False,
        capture_output=True,
        text=True,
        timeout=OLLAMA_WARMUP_TIMEOUT,
    )

    if result.stdout:
        print(result.stdout.rstrip(), flush=True)

    if result.stderr:
        print(result.stderr.rstrip(), flush=True)

    if result.returncode != 0:
        raise RuntimeError(f"Warmup failed with exit code {result.returncode}.")

    return time.perf_counter() - started


def run_request(user_text, memory):
    captured = io.StringIO()
    parts = []
    first_token = None
    started = time.perf_counter()

    try:
        with redirect_stdout(captured):
            stream = stream_ollama_response(
                user_text=user_text,
                history=memory.get_messages(),
                memory_context=memory.build_memory_context(),
            )

            for token in stream:
                if first_token is None:
                    first_token = time.perf_counter() - started

                parts.append(token)

    except (
        TimeoutError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        RuntimeError,
    ) as error:
        return {
            "success": False,
            "error": repr(error),
            "response": "",
            "first_token_seconds": first_token,
            "total_seconds": time.perf_counter() - started,
            "prompt_tokens": None,
            "response_tokens": None,
        }

    log = captured.getvalue()
    prompt_match = re.search(r"prompt_tokens=(\d+)", log)
    response_match = re.search(r"response_tokens=(\d+)", log)

    return {
        "success": True,
        "error": "",
        "response": "".join(parts).strip(),
        "first_token_seconds": first_token,
        "total_seconds": time.perf_counter() - started,
        "prompt_tokens": int(prompt_match.group(1)) if prompt_match else None,
        "response_tokens": int(response_match.group(1)) if response_match else None,
    }


def consolidate_if_needed(memory):
    if not memory.should_consolidate(
        max_active_turns=MEMORY_CONSOLIDATE_TURNS,
        max_history_characters=MEMORY_CONSOLIDATE_CHARACTERS,
    ):
        return None

    batch = memory.get_consolidation_batch(
        keep_recent_turns=MEMORY_KEEP_RECENT_TURNS,
    )

    if not batch:
        return None

    before = memory.get_stats()
    started = time.perf_counter()

    summary = consolidate_memory(
        existing_summary=memory.get_session_summary(),
        turns=batch,
    )

    elapsed = time.perf_counter() - started

    memory.apply_consolidation(
        new_summary=summary,
        consolidated_turn_count=len(batch),
    )

    after = memory.get_stats()

    return {
        "elapsed_seconds": elapsed,
        "before_turns": before["turn_count"],
        "after_turns": after["turn_count"],
        "summary_characters": after["summary_characters"],
        "summary": summary,
    }


def run_scenario(name, warmup_mode):
    print(f"\n=== {name.upper()} ===", flush=True)

    warmup_seconds = None

    if warmup_mode == "always":
        warmup_seconds = run_existing_warmup()
        print(
            f"[BENCHMARK] Warmup wall time: {warmup_seconds:.3f}s "
            "(reported separately; not part of turn latency).",
            flush=True,
        )
    else:
        print(
            "[BENCHMARK] Warmup skipped by request. "
            "The first turn may be a cold prompt evaluation.",
            flush=True,
        )

    memory = ShortTermMemory(max_turns=None)
    turn_rows = []
    recall_rows = []
    next_turn_is_cache_transition = False

    for turn_number, user_text in enumerate(TURN_PROMPTS, start=1):
        cache_transition_turn = next_turn_is_cache_transition
        next_turn_is_cache_transition = False

        if cache_transition_turn:
            print(
                "[CACHE TRANSITION] The previous request used the "
                "consolidator prompt. This turn measures switching back "
                "to the normal NANCEE prompt.",
                flush=True,
            )

        result = run_request(user_text, memory)

        if not result["success"]:
            print(
                f"[ERROR] turn={turn_number} {result['error']}",
                flush=True,
            )
            break

        memory.add_turn(
            user_text=user_text,
            assistant_text=result["response"],
        )

        consolidation = None

        if name == "consolidated":
            consolidation = consolidate_if_needed(memory)

            if consolidation is not None:
                next_turn_is_cache_transition = True

        stats = memory.get_stats()

        if consolidation:
            print(
                "[CONSOLIDATED] "
                f"{consolidation['before_turns']}->"
                f"{consolidation['after_turns']} turns, "
                f"{consolidation['elapsed_seconds']:.3f}s",
                flush=True,
            )
            print(
                f"[SUMMARY] {consolidation['summary']}",
                flush=True,
            )

        print(
            f"[TURN {turn_number:>2}] "
            f"stored={stats['turn_count']:>2} "
            f"history_chars={stats['history_characters']:>4} "
            f"context_chars={stats['memory_context_characters']:>4} "
            f"first={result['first_token_seconds']:.3f}s "
            f"total={result['total_seconds']:.3f}s "
            f"prompt_tokens={result['prompt_tokens']}",
            flush=True,
        )

        turn_rows.append(
            {
                "scenario": name,
                "turn_number": turn_number,
                "stored_turns": stats["turn_count"],
                "history_characters": stats["history_characters"],
                "memory_context_characters": stats["memory_context_characters"],
                "consolidation_count": stats["consolidation_count"],
                "consolidated_this_turn": bool(consolidation),
                "post_consolidation_cache_transition": cache_transition_turn,
                "warmup_seconds": warmup_seconds,
                "consolidation_seconds": (
                    consolidation["elapsed_seconds"] if consolidation else None
                ),
                "first_token_seconds": result["first_token_seconds"],
                "total_seconds": result["total_seconds"],
                "prompt_tokens": result["prompt_tokens"],
                "response_tokens": result["response_tokens"],
                "response": result["response"],
            }
        )

    print(f"\n[RECALL] {name}", flush=True)

    for fact_name, question, expected in RECALL_PROBES:
        result = run_request(question, memory)
        response = result["response"]
        passed = expected.casefold() in response.casefold()

        print(
            f"[{'PASS' if passed else 'FAIL'}] "
            f"{fact_name:<16} expected={expected!r} "
            f"response={response!r}",
            flush=True,
        )

        recall_rows.append(
            {
                "scenario": name,
                "fact_name": fact_name,
                "expected": expected,
                "passed": passed,
                "first_token_seconds": result["first_token_seconds"],
                "total_seconds": result["total_seconds"],
                "prompt_tokens": result["prompt_tokens"],
                "response": response,
                "error": result["error"],
            }
        )

    return turn_rows, recall_rows


def write_csv(path, rows):
    if not rows:
        return

    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)


def average(values):
    values = [value for value in values if value is not None]
    return statistics.mean(values) if values else 0.0


def main():
    args = parse_args()
    os.environ["NANCEE_MEMORY_DEBUG"] = "false"

    scenarios = ["baseline", "consolidated"] if args.mode == "both" else [args.mode]

    print(f"Model: {LLM_MODEL}")
    print(f"Scenarios: {scenarios}")
    print(
        "Consolidation settings: "
        f"turns={MEMORY_CONSOLIDATE_TURNS}, "
        f"characters={MEMORY_CONSOLIDATE_CHARACTERS}, "
        f"keep_recent={MEMORY_KEEP_RECENT_TURNS}",
        flush=True,
    )

    all_turn_rows = []
    all_recall_rows = []

    for scenario in scenarios:
        turn_rows, recall_rows = run_scenario(
            scenario,
            args.warmup,
        )
        all_turn_rows.extend(turn_rows)
        all_recall_rows.extend(recall_rows)

    print("\n=== COMPARISON ===")

    for scenario in scenarios:
        turns = [row for row in all_turn_rows if row["scenario"] == scenario]
        recalls = [row for row in all_recall_rows if row["scenario"] == scenario]
        first_token_values = [
            r["first_token_seconds"]
            for r in turns
            if r["first_token_seconds"] is not None
        ]
        steady_state_turns = [
            row
            for row in turns
            if int(row["turn_number"]) > 1
            and not row["post_consolidation_cache_transition"]
        ]
        steady_first_tokens = [
            row["first_token_seconds"]
            for row in steady_state_turns
            if row["first_token_seconds"] is not None
        ]
        transition_turns = [
            row for row in turns if row["post_consolidation_cache_transition"]
        ]
        transition_latency = (
            transition_turns[0]["first_token_seconds"] if transition_turns else None
        )

        print(
            f"{scenario}: "
            f"turns={len(turns)} "
            f"median_first="
            f"{statistics.median(first_token_values):.3f}s "
            f"steady_state_avg="
            f"{average(steady_first_tokens):.3f}s "
            f"post_consolidation_transition="
            f"{transition_latency:.3f}s "
            if transition_latency is not None
            else (
                f"{scenario}: "
                f"turns={len(turns)} "
                f"median_first="
                f"{statistics.median(first_token_values):.3f}s "
                f"steady_state_avg="
                f"{average(steady_first_tokens):.3f}s "
                "post_consolidation_transition=n/a "
            )
        )
        print(
            f"  final_prompt_tokens="
            f"{turns[-1]['prompt_tokens'] if turns else None} "
            f"recall={sum(1 for r in recalls if r['passed'])}/"
            f"{len(recalls)}"
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    turns_path = output_dir / f"memory_consolidation_turns_{timestamp}.csv"
    recall_path = output_dir / f"memory_consolidation_recall_{timestamp}.csv"

    write_csv(turns_path, all_turn_rows)
    write_csv(recall_path, all_recall_rows)

    print(f"\nTurn CSV: {turns_path}")
    print(f"Recall CSV: {recall_path}")


if __name__ == "__main__":
    main()
