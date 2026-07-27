#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark NANCEE's prepared-prefix TPC path against an exact "
            "prefix rebuild and a deliberately changed-prefix control."
        )
    )
    parser.add_argument(
        "--root",
        default=str(Path.home() / "Nancee" / "nancee"),
        help="NANCEE application root containing sherpa/ (default: ~/Nancee/nancee)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=8,
        help="Measured runs per mode (default: 8)",
    )
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=2,
        help="Discarded warmup rounds per mode (default: 2)",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory for CSV/JSON/raw logs (default: ~/Nancee-benchmarks)",
    )
    parser.add_argument(
        "--micro-iterations",
        type=int,
        default=5000,
        help="Iterations for Python-only prefix-build microbenchmark (default: 5000)",
    )
    return parser.parse_args()


def median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def format_seconds(value: float) -> str:
    return f"{value:.3f}s"


def main() -> int:
    args = parse_args()

    if args.runs <= 0:
        raise SystemExit("--runs must be positive")

    if args.warmup_runs < 0:
        raise SystemExit("--warmup-runs cannot be negative")

    root = Path(args.root).expanduser().resolve()
    sherpa_dir = root / "sherpa"

    if not sherpa_dir.is_dir():
        raise SystemExit(f"Sherpa directory does not exist: {sherpa_dir}")

    sys.path.insert(0, str(sherpa_dir))

    # Import only after placing sherpa/ on the module path.
    from config import LLM_MODEL  # type: ignore
    from ollama_runtime import (  # type: ignore
        build_ollama_prefix_messages,
        ensure_ollama_model_loaded,
        prime_ollama_context,
        stream_ollama_response,
    )
    from prompt_identity import json_sha256  # type: ignore

    output_dir = (
        Path(args.output_dir).expanduser()
        if args.output_dir
        else Path.home() / "Nancee-benchmarks"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_log_path = output_dir / f"tpc-benchmark-{stamp}.log"
    csv_path = output_dir / f"tpc-benchmark-{stamp}.csv"
    json_path = output_dir / f"tpc-benchmark-{stamp}.json"

    history = [
        {
            "role": "user",
            "content": "This is a stable benchmark history message.",
        },
        {
            "role": "assistant",
            "content": "Benchmark history acknowledged.",
        },
    ]
    stable_memory_context = ""

    stable_prefix = build_ollama_prefix_messages(
        history=history,
        memory_context=stable_memory_context,
    )
    stable_sha256 = json_sha256(stable_prefix)

    print(f"Model: {LLM_MODEL}")
    print(f"NANCEE root: {root}")
    print(f"Stable prefix messages: {len(stable_prefix)}")
    print(f"Stable prefix SHA256: {stable_sha256}")
    print(f"Measured runs per mode: {args.runs}")
    print(f"Discarded warmup rounds per mode: {args.warmup_runs}")
    print()

    print("Ensuring Ollama model is loaded and current warmup is valid...")
    ensure_ollama_model_loaded(LLM_MODEL)
    print("Model ready.")
    print()

    # Python-only benchmark. This measures the maximum app-level work saved
    # by avoiding one additional prefix construction and hash operation.
    micro_iterations = max(1, int(args.micro_iterations))

    started = time.perf_counter()
    for _ in range(micro_iterations):
        candidate = build_ollama_prefix_messages(
            history=history,
            memory_context=stable_memory_context,
        )
        json_sha256(candidate)
    build_hash_elapsed = time.perf_counter() - started
    build_hash_us = build_hash_elapsed / micro_iterations * 1_000_000.0

    started = time.perf_counter()
    for _ in range(micro_iterations):
        json_sha256(stable_prefix)
    hash_only_elapsed = time.perf_counter() - started
    hash_only_us = hash_only_elapsed / micro_iterations * 1_000_000.0

    print("Python-only prefix work:")
    print(f"  build + hash: {build_hash_us:.2f} microseconds per operation")
    print(f"  hash only:    {hash_only_us:.2f} microseconds per operation")
    print(
        "  This is expected to be tiny compared with model prompt evaluation; "
        "the snapshot contract mainly prevents drift."
    )
    print()

    records: list[dict[str, Any]] = []

    mode_descriptions = {
        "prepared_snapshot": (
            "Prime a canonical prefix, then pass that exact prepared snapshot "
            "into the real request."
        ),
        "rebuilt_same_prefix": (
            "Prime the canonical prefix, then make the request rebuild an "
            "identical prefix from the same history and memory context."
        ),
        "changed_prefix_control": (
            "Prime the canonical prefix, then request with a unique dynamic "
            "memory-context message so the full prefix cannot exactly match."
        ),
    }

    total_rounds = args.warmup_runs + args.runs

    with raw_log_path.open("w", encoding="utf-8") as raw_log:
        print(
            f"NANCEE TPC benchmark started {time.strftime('%Y-%m-%d %H:%M:%S')}",
            file=raw_log,
        )
        print(f"model={LLM_MODEL}", file=raw_log)
        print(f"stable_prefix_sha256={stable_sha256}", file=raw_log)
        print(file=raw_log)

        for round_index in range(total_rounds):
            measured = round_index >= args.warmup_runs
            phase = "MEASURED" if measured else "DISCARDED-WARMUP"
            measured_index = round_index - args.warmup_runs + 1

            # Rotate the mode order each round to reduce systematic ordering bias.
            mode_order = [
                "prepared_snapshot",
                "rebuilt_same_prefix",
                "changed_prefix_control",
            ]
            shift = round_index % len(mode_order)
            mode_order = mode_order[shift:] + mode_order[:shift]

            for mode in mode_order:
                label_index = measured_index if measured else round_index + 1
                print(
                    f"[{phase}] round={label_index} mode={mode}",
                    file=sys.stderr,
                    flush=True,
                )

                # Re-prime immediately before every request so each mode starts
                # from the intended canonical-prefix state.
                with contextlib.redirect_stdout(raw_log):
                    prime_result = prime_ollama_context(
                        prefix_messages=stable_prefix,
                    )

                unique_suffix = uuid.uuid4().hex[:12]
                user_text = (
                    "Reply with READY only. "
                    f"Benchmark sample {round_index + 1}-{unique_suffix}."
                )
                completion_state: dict[str, Any] = {}

                request_kwargs: dict[str, Any] = {
                    "user_text": user_text,
                    "history": history,
                    "retrieved_context": "",
                    "response_instruction": "Reply with READY only.",
                    "temperature": 0.0,
                    "num_predict": 1,
                    "completion_state": completion_state,
                }

                if mode == "prepared_snapshot":
                    request_kwargs.update(
                        memory_context=stable_memory_context,
                        prefix_messages=stable_prefix,
                        prefix_source="prepared_snapshot_benchmark",
                    )

                elif mode == "rebuilt_same_prefix":
                    request_kwargs.update(
                        memory_context=stable_memory_context,
                        prefix_messages=None,
                        prefix_source=None,
                    )

                elif mode == "changed_prefix_control":
                    request_kwargs.update(
                        memory_context=(
                            "BENCHMARK DYNAMIC PREFIX CONTROL "
                            f"{unique_suffix}"
                        ),
                        prefix_messages=None,
                        prefix_source=None,
                    )

                else:
                    raise RuntimeError(f"Unknown benchmark mode: {mode}")

                wall_started = time.perf_counter()

                with contextlib.redirect_stdout(raw_log):
                    tokens = list(
                        stream_ollama_response(
                            **request_kwargs,
                        )
                    )

                wall_seconds = time.perf_counter() - wall_started
                response_text = "".join(tokens).strip()

                record = {
                    "phase": phase,
                    "round": label_index,
                    "mode": mode,
                    "description": mode_descriptions[mode],
                    "response_text": response_text,
                    "wall_seconds": wall_seconds,
                    "first_token_seconds": float(
                        completion_state.get("first_token_seconds") or 0.0
                    ),
                    "total_seconds": float(
                        completion_state.get("total_seconds") or 0.0
                    ),
                    "load_seconds": float(
                        completion_state.get("load_seconds") or 0.0
                    ),
                    "prompt_eval_seconds": float(
                        completion_state.get("prompt_eval_seconds") or 0.0
                    ),
                    "generation_seconds": float(
                        completion_state.get("generation_seconds") or 0.0
                    ),
                    "prompt_tokens": int(
                        completion_state.get("prompt_tokens") or 0
                    ),
                    "response_tokens": int(
                        completion_state.get("response_tokens") or 0
                    ),
                    "prime_elapsed_seconds": float(
                        prime_result.get("elapsed_seconds") or 0.0
                    ),
                    "prime_prompt_eval_seconds": float(
                        prime_result.get("prompt_eval_seconds") or 0.0
                    ),
                    "stable_prefix_sha256": stable_sha256,
                }

                if measured:
                    records.append(record)

                print(json.dumps(record, sort_keys=True), file=raw_log)
                raw_log.flush()

                time.sleep(0.15)

    fieldnames = list(records[0].keys()) if records else []

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    summary: dict[str, Any] = {
        "model": LLM_MODEL,
        "stable_prefix_sha256": stable_sha256,
        "runs_per_mode": args.runs,
        "discarded_warmup_runs_per_mode": args.warmup_runs,
        "python_microbenchmark": {
            "iterations": micro_iterations,
            "build_and_hash_microseconds": build_hash_us,
            "hash_only_microseconds": hash_only_us,
        },
        "modes": {},
        "raw_records": records,
    }

    metric_names = (
        "first_token_seconds",
        "prompt_eval_seconds",
        "total_seconds",
        "wall_seconds",
        "load_seconds",
        "generation_seconds",
        "prime_elapsed_seconds",
    )

    for mode in mode_descriptions:
        mode_records = [
            record for record in records
            if record["mode"] == mode
        ]
        mode_summary: dict[str, Any] = {
            "description": mode_descriptions[mode],
            "count": len(mode_records),
            "metrics": {},
        }

        for metric in metric_names:
            values = [
                float(record[metric])
                for record in mode_records
            ]
            mode_summary["metrics"][metric] = {
                "median": median(values),
                "mean": mean(values),
                "minimum": min(values) if values else 0.0,
                "p90": percentile(values, 0.90),
                "maximum": max(values) if values else 0.0,
            }

        summary["modes"][mode] = mode_summary

    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print()
    print("RESULTS — medians")
    print(
        f"{'Mode':<25}"
        f"{'First token':>14}"
        f"{'Prompt eval':>14}"
        f"{'Total':>12}"
        f"{'Wall':>12}"
    )
    print("-" * 77)

    for mode in mode_descriptions:
        metrics = summary["modes"][mode]["metrics"]
        print(
            f"{mode:<25}"
            f"{format_seconds(metrics['first_token_seconds']['median']):>14}"
            f"{format_seconds(metrics['prompt_eval_seconds']['median']):>14}"
            f"{format_seconds(metrics['total_seconds']['median']):>12}"
            f"{format_seconds(metrics['wall_seconds']['median']):>12}"
        )

    prepared = summary["modes"]["prepared_snapshot"]["metrics"]
    rebuilt = summary["modes"]["rebuilt_same_prefix"]["metrics"]
    changed = summary["modes"]["changed_prefix_control"]["metrics"]

    prepared_ft = prepared["first_token_seconds"]["median"]
    rebuilt_ft = rebuilt["first_token_seconds"]["median"]
    changed_ft = changed["first_token_seconds"]["median"]

    print()
    print("INTERPRETATION")
    print(
        "1. prepared_snapshot vs rebuilt_same_prefix should usually be close. "
        "Both send the same serialized prefix to Ollama, so the application "
        "snapshot handoff is primarily a correctness/reliability improvement."
    )
    print(
        "2. changed_prefix_control should generally be slower because the "
        "canonical prefix cannot match through the dynamic context."
    )

    if rebuilt_ft > 0:
        difference_ms = (rebuilt_ft - prepared_ft) * 1000.0
        print(
            "3. Median prepared-vs-rebuilt first-token difference: "
            f"{difference_ms:+.1f} ms."
        )

    if changed_ft > 0 and prepared_ft > 0:
        improvement = (changed_ft - prepared_ft) / changed_ft * 100.0
        print(
            "4. Prepared snapshot first-token improvement over changed-prefix "
            f"control: {improvement:.1f}%."
        )

    print()
    print(f"Raw log: {raw_log_path}")
    print(f"CSV:     {csv_path}")
    print(f"JSON:    {json_path}")
    print()
    print(
        "Paste the RESULTS table and the JSON summary if you want the run "
        "interpreted."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

