#!/usr/bin/env python3
"""
Benchmark NANCEE active-buffer + external-session-archive memory.

This benchmark does not call the LLM consolidator. Older turns are moved
out of the live prompt instantly, then relevant archived turns are
retrieved with local Python token matching.

Recommended first run:

    /usr/local/bin/nancee-ollama-warmup phi4-mini:3.8b
    python3 -B benchmark_active_archive.py \
        --mode archive \
        --turns 24 \
        --warmup skip

Longer run:

    python3 -B benchmark_active_archive.py \
        --mode archive \
        --turns 36 \
        --warmup always
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

from config import (
    LLM_MODEL,
    MEMORY_ACTIVE_CHARACTER_LIMIT,
    MEMORY_ACTIVE_TURN_LIMIT,
    MEMORY_KEEP_RECENT_TURNS,
    MEMORY_RETRIEVAL_LIMIT,
    MEMORY_RETRIEVAL_MIN_SCORE,
    OLLAMA_WARMUP_COMMAND,
    OLLAMA_WARMUP_TIMEOUT,
)
from ollama_runtime import stream_ollama_response
from session_archive import (
    SessionArchive,
    archive_active_memory_if_needed,
)
from short_term_memory import ShortTermMemory

FACT_TURNS = {
    1: "My name is Anders. Remember that. Reply with one short sentence.",
    3: ("My daughter is named Copeland. Remember that. Reply with one short sentence."),
    6: (
        "My favorite road-trip snack is mango slices. Remember that. "
        "Reply with one short sentence."
    ),
    10: (
        "The exact test code is ORBIT-731. Remember it exactly. "
        "Reply with one short sentence."
    ),
    15: (
        "Today's destination is the ice skating rink. Remember that. "
        "Reply with one short sentence."
    ),
    20: (
        "My trucker buddy calls his truck Blue Mule. Remember that. "
        "Reply with one short sentence."
    ),
}

RECALL_PROBES = [
    ("user_name", "What is my name?", "Anders"),
    ("daughter_name", "What is my daughter's name?", "Copeland"),
    (
        "road_trip_snack",
        "What is my favorite road-trip snack?",
        "mango",
    ),
    (
        "test_code",
        "What exact test code did I ask you to remember?",
        "ORBIT-731",
    ),
    ("destination", "What is today's destination?", "ice skating rink"),
    (
        "truck_name",
        "What does my trucker buddy call his truck?",
        "Blue Mule",
    ),
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("baseline", "archive", "both"),
        default="archive",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=24,
    )
    parser.add_argument(
        "--warmup",
        choices=("always", "skip"),
        default="always",
    )
    parser.add_argument(
        "--output-dir",
        default="memory_benchmark_results",
    )
    return parser.parse_args()


def build_turn_prompt(turn_number):
    if turn_number in FACT_TURNS:
        return FACT_TURNS[turn_number]

    return (
        f"This is ordinary conversation turn {turn_number}. "
        "We are continuing a relaxed drive. Reply with one short sentence."
    )


def run_existing_warmup():
    print(
        f"[BENCHMARK] Running existing warmup: {OLLAMA_WARMUP_COMMAND} {LLM_MODEL}",
        flush=True,
    )

    started = time.perf_counter()
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


def run_request(
    *,
    user_text,
    memory,
    retrieved_context,
):
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
                retrieved_context=retrieved_context,
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

    runtime_log = captured.getvalue()
    prompt_match = re.search(r"prompt_tokens=(\d+)", runtime_log)
    response_match = re.search(r"response_tokens=(\d+)", runtime_log)

    return {
        "success": True,
        "error": "",
        "response": "".join(parts).strip(),
        "first_token_seconds": first_token,
        "total_seconds": time.perf_counter() - started,
        "prompt_tokens": (int(prompt_match.group(1)) if prompt_match else None),
        "response_tokens": (int(response_match.group(1)) if response_match else None),
    }


def run_scenario(name, total_turns, warmup_mode):
    print(f"\n=== {name.upper()} ===", flush=True)

    if warmup_mode == "always":
        warmup_seconds = run_existing_warmup()
        print(
            f"[BENCHMARK] Warmup wall time: {warmup_seconds:.3f}s",
            flush=True,
        )
    else:
        warmup_seconds = None
        print(
            "[BENCHMARK] Warmup skipped. Run the existing warmup "
            "manually immediately before this command.",
            flush=True,
        )

    memory = ShortTermMemory(max_turns=None)
    archive = SessionArchive()
    turn_rows = []
    recall_rows = []
    next_turn_is_archive_transition = False

    for turn_number in range(1, total_turns + 1):
        user_text = build_turn_prompt(turn_number)

        # Isolation test:
        # archive old turns, but do not retrieve archive entries
        # during ordinary benchmark conversation.
        retrieved_turns = []
        retrieved_context = ""

        archive_transition = next_turn_is_archive_transition
        next_turn_is_archive_transition = False

        result = run_request(
            user_text=user_text,
            memory=memory,
            retrieved_context=retrieved_context,
        )

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

        moved = []
        archive_elapsed = None

        if name == "archive":
            archive_started = time.perf_counter()
            moved = archive_active_memory_if_needed(
                memory=memory,
                archive=archive,
                max_active_turns=MEMORY_ACTIVE_TURN_LIMIT,
                max_active_characters=(MEMORY_ACTIVE_CHARACTER_LIMIT),
                keep_recent_turns=MEMORY_KEEP_RECENT_TURNS,
            )
            archive_elapsed = time.perf_counter() - archive_started

            if moved:
                next_turn_is_archive_transition = True

        memory_stats = memory.get_stats()
        archive_stats = archive.get_stats()

        transition_text = " CACHE-TRANSITION" if archive_transition else ""
        moved_text = f" archived_now={len(moved)}" if moved else ""

        print(
            f"[TURN {turn_number:>2}] "
            f"active={memory_stats['turn_count']:>2} "
            f"archived={archive_stats['turn_count']:>2} "
            f"retrieved={len(retrieved_turns)} "
            f"first={result['first_token_seconds']:.3f}s "
            f"total={result['total_seconds']:.3f}s "
            f"prompt_tokens={result['prompt_tokens']}"
            f"{moved_text}{transition_text}",
            flush=True,
        )

        turn_rows.append(
            {
                "scenario": name,
                "turn_number": turn_number,
                "active_turns": memory_stats["turn_count"],
                "archived_turns": archive_stats["turn_count"],
                "retrieved_turns": len(retrieved_turns),
                "retrieved_archive_ids": ",".join(
                    str(item["archive_id"]) for item in retrieved_turns
                ),
                "archived_this_turn": len(moved),
                "archive_operation_seconds": archive_elapsed,
                "post_archive_cache_transition": archive_transition,
                "first_token_seconds": result["first_token_seconds"],
                "total_seconds": result["total_seconds"],
                "prompt_tokens": result["prompt_tokens"],
                "response_tokens": result["response_tokens"],
                "response": result["response"],
            }
        )

    print(f"\n[RECALL] {name}", flush=True)

    for fact_name, question, expected in RECALL_PROBES:
        retrieved_turns = []

        if name == "archive":
            retrieved_turns = archive.retrieve(
                question,
                limit=MEMORY_RETRIEVAL_LIMIT,
                min_score=MEMORY_RETRIEVAL_MIN_SCORE,
            )

        retrieved_context = archive.format_retrieved_context(retrieved_turns)

        result = run_request(
            user_text=question,
            memory=memory,
            retrieved_context=retrieved_context,
        )

        response = result["response"]
        passed = expected.casefold() in response.casefold()

        print(
            f"[{'PASS' if passed else 'FAIL'}] "
            f"{fact_name:<16} "
            f"retrieved={len(retrieved_turns)} "
            f"expected={expected!r} "
            f"response={response!r}",
            flush=True,
        )

        recall_rows.append(
            {
                "scenario": name,
                "fact_name": fact_name,
                "expected": expected,
                "passed": passed,
                "retrieved_turns": len(retrieved_turns),
                "retrieved_archive_ids": ",".join(
                    str(item["archive_id"]) for item in retrieved_turns
                ),
                "first_token_seconds": result["first_token_seconds"],
                "total_seconds": result["total_seconds"],
                "prompt_tokens": result["prompt_tokens"],
                "response": response,
                "error": result["error"],
            }
        )

    return turn_rows, recall_rows


def average(values):
    values = [value for value in values if value is not None]
    return statistics.mean(values) if values else 0.0


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


def print_comparison(scenarios, turn_rows, recall_rows):
    print("\n=== COMPARISON ===")

    for scenario in scenarios:
        turns = [row for row in turn_rows if row["scenario"] == scenario]
        recalls = [row for row in recall_rows if row["scenario"] == scenario]

        first_values = [
            row["first_token_seconds"]
            for row in turns
            if row["first_token_seconds"] is not None
        ]
        transition_values = [
            row["first_token_seconds"]
            for row in turns
            if row["post_archive_cache_transition"]
            and row["first_token_seconds"] is not None
        ]
        normal_values = [
            row["first_token_seconds"]
            for row in turns
            if not row["post_archive_cache_transition"]
            and row["first_token_seconds"] is not None
        ]

        print(
            f"{scenario}: "
            f"turns={len(turns)} "
            f"median_first={statistics.median(first_values):.3f}s "
            f"normal_avg={average(normal_values):.3f}s "
            f"transition_avg={average(transition_values):.3f}s "
            f"max_first={max(first_values):.3f}s "
            f"final_prompt_tokens="
            f"{turns[-1]['prompt_tokens'] if turns else None} "
            f"recall={sum(1 for row in recalls if row['passed'])}/"
            f"{len(recalls)}"
        )


def main():
    args = parse_args()

    if args.turns < max(FACT_TURNS):
        raise SystemExit(f"--turns must be at least {max(FACT_TURNS)}.")

    os.environ["NANCEE_MEMORY_DEBUG"] = "false"

    scenarios = ["baseline", "archive"] if args.mode == "both" else [args.mode]

    print(f"Model: {LLM_MODEL}")
    print(f"Scenarios: {scenarios}")
    print(f"Turns: {args.turns}")
    print(
        "Archive settings: "
        f"active_turns={MEMORY_ACTIVE_TURN_LIMIT}, "
        f"active_characters={MEMORY_ACTIVE_CHARACTER_LIMIT}, "
        f"keep_recent={MEMORY_KEEP_RECENT_TURNS}, "
        f"retrieve={MEMORY_RETRIEVAL_LIMIT}, "
        f"min_score={MEMORY_RETRIEVAL_MIN_SCORE}",
        flush=True,
    )

    all_turn_rows = []
    all_recall_rows = []

    for scenario in scenarios:
        turn_rows, recall_rows = run_scenario(
            scenario,
            args.turns,
            args.warmup,
        )
        all_turn_rows.extend(turn_rows)
        all_recall_rows.extend(recall_rows)

    print_comparison(
        scenarios,
        all_turn_rows,
        all_recall_rows,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    turns_path = output_dir / f"active_archive_turns_{timestamp}.csv"
    recall_path = output_dir / f"active_archive_recall_{timestamp}.csv"

    write_csv(turns_path, all_turn_rows)
    write_csv(recall_path, all_recall_rows)

    print(f"\nTurn CSV: {turns_path}")
    print(f"Recall CSV: {recall_path}")


if __name__ == "__main__":
    main()
