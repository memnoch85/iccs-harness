#!/usr/bin/env python3
"""
Benchmark NANCEE short-term memory using the real sequential chat path.

This script deliberately does NOT modify NANCEE's working warmup code.
Instead, it executes the existing OLLAMA_WARMUP_COMMAND before each
benchmark scenario, then grows conversation history one turn at a time.

That matters because NANCEE normally does this:

    empty history
    -> turn 1
    -> turn 2
    -> turn 3
    -> ...

It does not normally create 40 turns in Python and send all 40 to Ollama
for the first time in one request.

Run from the sherpa directory:

    python3 -B benchmark_short_term_memory_v3.py

Recommended first comparison:

    python3 -B benchmark_short_term_memory_v3.py \
        --windows 30,40,unbounded \
        --total-turns 45

A longer comparison:

    python3 -B benchmark_short_term_memory_v3.py \
        --windows 10,20,30,40,unbounded \
        --total-turns 50
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import statistics
import subprocess
import sys
import urllib.error
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Optional

from config import (
    LLM_MODEL,
    OLLAMA_WARMUP_COMMAND,
    OLLAMA_WARMUP_TIMEOUT,
)
from ollama_runtime import stream_ollama_response
from short_term_memory import ShortTermMemory


@dataclass(frozen=True)
class FactSpec:
    age_turns: int
    name: str
    value: str


FACT_SPECS = (
    FactSpec(44, "oldest route code", "ORBIT-731"),
    FactSpec(34, "mountain snack code", "MANGO-482"),
    FactSpec(24, "garage music code", "RAVEN-265"),
    FactSpec(14, "hiking boot code", "CEDAR-914"),
    FactSpec(4, "newest fuel code", "EMBER-308"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark NANCEE memory by growing real conversation history "
            "sequentially and measuring recall plus latency."
        )
    )
    parser.add_argument(
        "--windows",
        default="30,40,unbounded",
        help=(
            "Comma-separated turn windows. Use unbounded/none for no limit. "
            "Default: 30,40,unbounded"
        ),
    )
    parser.add_argument(
        "--total-turns",
        type=int,
        default=45,
        help="Completed synthetic turns per scenario. Default: 45",
    )
    parser.add_argument(
        "--output-dir",
        default="memory_benchmark_results",
        help="CSV output directory. Default: memory_benchmark_results",
    )
    return parser.parse_args()


def parse_windows(raw: str) -> list[Optional[int]]:
    windows: list[Optional[int]] = []

    for item in raw.split(","):
        value = item.strip().lower()

        if value in {"none", "unbounded", "unlimited"}:
            windows.append(None)
            continue

        try:
            parsed = int(value)
        except ValueError as error:
            raise ValueError(f"Invalid window: {item!r}") from error

        if parsed <= 0:
            raise ValueError("Window values must be positive integers.")

        windows.append(parsed)

    if not windows:
        raise ValueError("At least one window is required.")

    return windows


def validate_total_turns(total_turns: int) -> None:
    oldest_age = max(fact.age_turns for fact in FACT_SPECS)

    if total_turns <= oldest_age:
        raise ValueError(f"--total-turns must be greater than {oldest_age}.")


def window_label(max_turns: Optional[int]) -> str:
    return "unbounded" if max_turns is None else str(max_turns)


def run_existing_warmup() -> None:
    """
    Execute NANCEE's existing, already-working warmup unchanged.

    The benchmark does not reproduce or replace its logic.
    """
    print(
        f"[BENCHMARK] Running existing warmup command: "
        f"{OLLAMA_WARMUP_COMMAND} {LLM_MODEL}",
        flush=True,
    )

    try:
        result = subprocess.run(
            [
                OLLAMA_WARMUP_COMMAND,
                LLM_MODEL,
            ],
            check=False,
            text=True,
            capture_output=True,
            timeout=OLLAMA_WARMUP_TIMEOUT,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Existing warmup timed out after {OLLAMA_WARMUP_TIMEOUT} seconds."
        ) from error
    except OSError as error:
        raise RuntimeError(
            f"Could not execute existing warmup command "
            f"{OLLAMA_WARMUP_COMMAND!r}: {error}"
        ) from error

    if result.stdout:
        print(result.stdout.rstrip(), flush=True)

    if result.stderr:
        print(result.stderr.rstrip(), flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Existing warmup failed with exit code {result.returncode}."
        )


def fact_turn_number(
    total_turns: int,
    fact: FactSpec,
) -> int:
    return total_turns - fact.age_turns


def build_turn_text(
    turn_number: int,
    total_turns: int,
) -> str:
    for fact in FACT_SPECS:
        if turn_number == fact_turn_number(total_turns, fact):
            return (
                f"Benchmark turn {turn_number}. "
                f"Remember this exact fact: the {fact.name} is "
                f"{fact.value}. Reply with one short acknowledgement."
            )

    return (
        f"Benchmark turn {turn_number}. "
        "This is an ordinary driving conversation filler with no new "
        "code or personal fact. Reply with one short acknowledgement."
    )


def run_streamed_request(
    *,
    user_text: str,
    history: list[dict[str, str]],
    memory_context: Optional[str],
) -> dict[str, object]:
    """
    Use NANCEE's real stream_ollama_response() and capture its timing data.
    """
    captured_stdout = io.StringIO()
    response_parts: list[str] = []
    first_token_seconds: Optional[float] = None
    started = perf_counter()

    try:
        with redirect_stdout(captured_stdout):
            response_stream = stream_ollama_response(
                user_text=user_text,
                history=history,
                memory_context=memory_context,
            )

            for token in response_stream:
                if first_token_seconds is None:
                    first_token_seconds = perf_counter() - started

                response_parts.append(token)

    except (
        TimeoutError,
        urllib.error.URLError,
        urllib.error.HTTPError,
    ) as error:
        return {
            "success": False,
            "error": repr(error),
            "response": "",
            "first_token_seconds": first_token_seconds,
            "total_seconds": perf_counter() - started,
            "prompt_tokens": None,
            "response_tokens": None,
            "runtime_log": captured_stdout.getvalue(),
        }

    total_seconds = perf_counter() - started
    runtime_log = captured_stdout.getvalue()
    response_text = "".join(response_parts).strip()

    prompt_match = re.search(
        r"prompt_tokens=(\d+)",
        runtime_log,
    )
    response_match = re.search(
        r"response_tokens=(\d+)",
        runtime_log,
    )

    return {
        "success": True,
        "error": "",
        "response": response_text,
        "first_token_seconds": first_token_seconds,
        "total_seconds": total_seconds,
        "prompt_tokens": (int(prompt_match.group(1)) if prompt_match else None),
        "response_tokens": (int(response_match.group(1)) if response_match else None),
        "runtime_log": runtime_log,
    }


def value_is_in_history(
    history: list[dict[str, str]],
    value: str,
) -> bool:
    expected = value.casefold()

    return any(
        expected in str(message.get("content", "")).casefold() for message in history
    )


def mean_or_none(values: list[Optional[float]]) -> Optional[float]:
    clean = [float(value) for value in values if value is not None]

    return statistics.mean(clean) if clean else None


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fieldnames: list[str],
) -> None:
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def run_window_scenario(
    *,
    max_turns: Optional[int],
    total_turns: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    label = window_label(max_turns)
    memory = ShortTermMemory(max_turns=max_turns)
    turn_rows: list[dict[str, object]] = []
    recall_rows: list[dict[str, object]] = []

    print(
        f"\n=== SCENARIO window={label} ===",
        flush=True,
    )

    # Use the existing two-pass warmup exactly as NANCEE already defines it.
    run_existing_warmup()

    for turn_number in range(1, total_turns + 1):
        before_stats = memory.get_stats()
        user_text = build_turn_text(
            turn_number=turn_number,
            total_turns=total_turns,
        )

        result = run_streamed_request(
            user_text=user_text,
            history=memory.get_messages(),
            memory_context=memory.build_memory_context(),
        )

        if not result["success"]:
            print(
                f"[TIMEOUT/ERROR] window={label} turn={turn_number} "
                f"stored_before={before_stats['turn_count']} "
                f"error={result['error']}",
                flush=True,
            )
            turn_rows.append(
                {
                    "window": label,
                    "turn_number": turn_number,
                    "stored_turns_before": before_stats["turn_count"],
                    "stored_turns_after": before_stats["turn_count"],
                    "history_characters_before": (before_stats["history_characters"]),
                    "eviction_begins_here": (
                        max_turns is not None and turn_number == max_turns + 1
                    ),
                    "success": False,
                    "first_token_seconds": result["first_token_seconds"],
                    "total_seconds": result["total_seconds"],
                    "prompt_tokens": result["prompt_tokens"],
                    "response_tokens": result["response_tokens"],
                    "error": result["error"],
                }
            )
            break

        assistant_text = str(result["response"]).strip()

        if not assistant_text:
            print(
                f"[ERROR] Empty response at window={label}, turn={turn_number}.",
                flush=True,
            )
            break

        memory.add_turn(
            user_text=user_text,
            assistant_text=assistant_text,
        )
        after_stats = memory.get_stats()

        eviction_boundary = max_turns is not None and turn_number == max_turns + 1

        marker = " <== FIRST EVICTION" if eviction_boundary else ""

        print(
            f"[TURN {turn_number:>2}] "
            f"stored={after_stats['turn_count']:>2} "
            f"chars={after_stats['history_characters']:>5} "
            f"first={result['first_token_seconds']:.3f}s "
            f"total={result['total_seconds']:.3f}s "
            f"prompt_tokens={result['prompt_tokens']}"
            f"{marker}",
            flush=True,
        )

        turn_rows.append(
            {
                "window": label,
                "turn_number": turn_number,
                "stored_turns_before": before_stats["turn_count"],
                "stored_turns_after": after_stats["turn_count"],
                "history_characters_before": (before_stats["history_characters"]),
                "eviction_begins_here": eviction_boundary,
                "success": True,
                "first_token_seconds": result["first_token_seconds"],
                "total_seconds": result["total_seconds"],
                "prompt_tokens": result["prompt_tokens"],
                "response_tokens": result["response_tokens"],
                "error": "",
            }
        )

    print(
        f"\n[RECALL] Probing retained and evicted facts for window={label}",
        flush=True,
    )

    history = memory.get_messages()
    memory_context = memory.build_memory_context()

    for fact in FACT_SPECS:
        present = value_is_in_history(
            history=history,
            value=fact.value,
        )
        question = (
            "This is a memory benchmark. "
            f"What is the {fact.name}? "
            "Answer with the exact code only. "
            "If the code is not present in conversation history, "
            "answer UNKNOWN."
        )

        result = run_streamed_request(
            user_text=question,
            history=history,
            memory_context=memory_context,
        )

        response = str(result["response"])
        recalled = fact.value.casefold() in response.casefold()
        answered_unknown = "unknown" in response.casefold()

        correct = recalled if present else answered_unknown

        print(
            f"[{'PASS' if correct else 'FAIL'}] "
            f"age={fact.age_turns:>2} "
            f"{'present' if present else 'evicted':<7} "
            f"expected={fact.value:<10} "
            f"response={response!r}",
            flush=True,
        )

        recall_rows.append(
            {
                "window": label,
                "fact_name": fact.name,
                "fact_value": fact.value,
                "fact_age_turns": fact.age_turns,
                "present_in_history": present,
                "request_success": result["success"],
                "recalled": recalled,
                "answered_unknown": answered_unknown,
                "correct_behavior": correct,
                "first_token_seconds": result["first_token_seconds"],
                "total_seconds": result["total_seconds"],
                "prompt_tokens": result["prompt_tokens"],
                "response": response,
                "error": result["error"],
            }
        )

    return turn_rows, recall_rows


def print_summary(
    *,
    windows: list[Optional[int]],
    turn_rows: list[dict[str, object]],
    recall_rows: list[dict[str, object]],
) -> None:
    print("\n=== SUMMARY ===")

    for max_turns in windows:
        label = window_label(max_turns)
        scenario_turns = [
            row for row in turn_rows if row["window"] == label and row["success"]
        ]
        scenario_recalls = [row for row in recall_rows if row["window"] == label]

        average_first = mean_or_none(
            [row["first_token_seconds"] for row in scenario_turns]
        )
        correct_recalls = sum(1 for row in scenario_recalls if row["correct_behavior"])

        boundary_rows = [row for row in scenario_turns if row["eviction_begins_here"]]
        boundary_first = (
            boundary_rows[0]["first_token_seconds"] if boundary_rows else None
        )

        print(
            f"window={label:<9} "
            f"completed_turns={len(scenario_turns):>2} "
            f"avg_first_token="
            f"{average_first:.3f}s "
            if average_first is not None
            else f"window={label:<9} completed_turns=0 "
        )

        print(
            f"  recall_correct={correct_recalls}/"
            f"{len(scenario_recalls)} "
            f"first_eviction_latency="
            f"{boundary_first:.3f}s"
            if boundary_first is not None
            else (
                f"  recall_correct={correct_recalls}/"
                f"{len(scenario_recalls)} "
                "first_eviction_latency=n/a"
            )
        )


def main() -> int:
    args = parse_args()

    try:
        windows = parse_windows(args.windows)
        validate_total_turns(args.total_turns)
    except ValueError as error:
        print(
            f"Configuration error: {error}",
            file=sys.stderr,
        )
        return 2

    # Keep benchmark output readable.
    os.environ["NANCEE_MEMORY_DEBUG"] = "false"

    output_dir = Path(args.output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"Model: {LLM_MODEL}")
    print(f"Windows: {[window_label(value) for value in windows]}")
    print(f"Sequential turns per scenario: {args.total_turns}")
    print(
        "Warmup: existing NANCEE warmup command, unchanged",
        flush=True,
    )

    all_turn_rows: list[dict[str, object]] = []
    all_recall_rows: list[dict[str, object]] = []

    for max_turns in windows:
        scenario_turns, scenario_recalls = run_window_scenario(
            max_turns=max_turns,
            total_turns=args.total_turns,
        )
        all_turn_rows.extend(scenario_turns)
        all_recall_rows.extend(scenario_recalls)

    turn_path = output_dir / f"memory_sequential_turns_{timestamp}.csv"
    recall_path = output_dir / f"memory_sequential_recall_{timestamp}.csv"

    write_csv(
        path=turn_path,
        rows=all_turn_rows,
        fieldnames=[
            "window",
            "turn_number",
            "stored_turns_before",
            "stored_turns_after",
            "history_characters_before",
            "eviction_begins_here",
            "success",
            "first_token_seconds",
            "total_seconds",
            "prompt_tokens",
            "response_tokens",
            "error",
        ],
    )
    write_csv(
        path=recall_path,
        rows=all_recall_rows,
        fieldnames=[
            "window",
            "fact_name",
            "fact_value",
            "fact_age_turns",
            "present_in_history",
            "request_success",
            "recalled",
            "answered_unknown",
            "correct_behavior",
            "first_token_seconds",
            "total_seconds",
            "prompt_tokens",
            "response",
            "error",
        ],
    )

    print_summary(
        windows=windows,
        turn_rows=all_turn_rows,
        recall_rows=all_recall_rows,
    )

    print(f"\nTurn CSV: {turn_path}")
    print(f"Recall CSV: {recall_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
