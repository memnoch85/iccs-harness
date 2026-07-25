#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHERPA = ROOT / "sherpa"

if str(SHERPA) not in sys.path:
    sys.path.insert(0, str(SHERPA))

from config import LLM_MODEL  # noqa: E402
from input_router import route_user_input  # noqa: E402
from ollama_runtime import (  # noqa: E402
    create_ollama_tpc,
    ensure_ollama_model_loaded,
    stream_ollama_response,
)
from profile_fact_index import ProfileFactIndex  # noqa: E402
from response_policy import response_policy_for_route  # noqa: E402
from session_archive import SessionArchive  # noqa: E402
from session_memory_store import filter_memory_hits_by_overlap  # noqa: E402
from short_term_memory import ShortTermMemory  # noqa: E402


@dataclass(frozen=True)
class BenchmarkCase:
    label: str
    text: str
    expected_route: str
    previous_assistant: str | None = None


CASES = (
    BenchmarkCase("greeting_1", "Hello Nancee, how are you?", "greeting"),
    BenchmarkCase("normal_fact_1", "What is the capital of France?", "normal"),
    BenchmarkCase("detailed_1", "Explain step by step how a turbocharger works.", "detailed"),
    BenchmarkCase("directive_1", "Ask me whether I finished wiring the power board.", "directive"),
    BenchmarkCase("context_answer_1", "I sure did.", "clarify", "Did you finish wiring the power board?"),
    BenchmarkCase("recall_context_1", "Do you remember what I finished wiring?", "recall"),
    BenchmarkCase("clarify_1", "Hardly drive.", "clarify"),
    BenchmarkCase("update_1", "Today I bought a brass compass at Harbor Market.", "acknowledge"),
    BenchmarkCase("recall_1", "What did I buy at Harbor Market?", "recall"),
    BenchmarkCase("profile_recall_1", "What color is my vehicle?", "recall"),
    BenchmarkCase("greeting_2", "Thanks.", "greeting"),
    BenchmarkCase("detailed_2", "Compare a turbocharger and a supercharger.", "detailed"),
    BenchmarkCase("directive_2", "Tell me a short joke.", "directive"),
    BenchmarkCase("normal_fact_2", "What is the capital of Japan?", "normal"),
    BenchmarkCase("update_2", "My dad's name is Daniel.", "acknowledge"),
    BenchmarkCase("recall_2", "What is my dad's name?", "recall"),
    BenchmarkCase("normal_question_1", "Why does an engine need oil?", "detailed"),
    BenchmarkCase("directive_3", "Ask me whether the headset is connected.", "directive"),
    BenchmarkCase("context_answer_2", "Nope.", "clarify", "Are you wearing the headset?"),
    BenchmarkCase("recall_context_2", "Do you remember whether I am wearing the headset?", "recall"),
    BenchmarkCase("update_3", "I finished installing the CAN hat today.", "acknowledge"),
    BenchmarkCase("recall_3", "What did I finish installing?", "recall"),
    BenchmarkCase("clarify_2", "Barely started.", "clarify"),
    BenchmarkCase("greeting_3", "Good morning Nancee.", "greeting"),
    BenchmarkCase("detailed_3", "Explain why fuel trims matter.", "detailed"),
    BenchmarkCase("normal_fact_3", "What is the largest planet?", "normal"),
    BenchmarkCase("update_4", "I parked on level three near the west elevator.", "acknowledge"),
    BenchmarkCase("recall_4", "Where did I park?", "recall"),
    BenchmarkCase("directive_4", "Name France's capital.", "directive"),
    BenchmarkCase("normal_fact_4", "What is two plus two?", "normal"),
)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return float(ordered[index])


def retrieve_context(
    recall_memory: SessionArchive,
    query: str,
    *,
    allow_weak_match: bool,
) -> str:
    hits = recall_memory.retrieve(query, limit=3)
    hits = filter_memory_hits_by_overlap(
        query,
        hits,
        minimum_overlap=2,
        allow_weak_match=allow_weak_match,
    )
    return recall_memory.format_related_context(hits, max_characters=650)


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0}

    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": percentile(values, 0.95),
    }


def write_summary(path: Path, *, mode: str, rows: list[dict[str, object]]) -> None:
    # Turn one includes the post-model-load/startup-cache shape and is useful,
    # but steady-state turns are the more important TPC comparison.
    steady_rows = rows[1:] if len(rows) > 1 else rows

    def values(source, key):
        return [float(row[key]) for row in source]

    summary = {
        "mode": mode,
        "question_count": len(rows),
        "steady_state_question_count": len(steady_rows),
        "route": _stats(values(rows, "route_seconds")),
        "first_token": _stats(values(rows, "first_token_seconds")),
        "foreground_first_token": _stats(
            values(rows, "foreground_first_token_seconds")
        ),
        "prompt_eval": _stats(values(rows, "prompt_eval_seconds")),
        "request_total": _stats(values(rows, "request_total_seconds")),
        "foreground_total": _stats(values(rows, "foreground_total_seconds")),
        "steady_state": {
            "foreground_first_token": _stats(
                values(steady_rows, "foreground_first_token_seconds")
            ),
            "prompt_eval": _stats(values(steady_rows, "prompt_eval_seconds")),
            "foreground_total": _stats(
                values(steady_rows, "foreground_total_seconds")
            ),
        },
        "tpc_wait": {
            **_stats(values(rows, "tpc_wait_seconds")),
            "max": max(values(rows, "tpc_wait_seconds")),
            "total": sum(values(rows, "tpc_wait_seconds")),
        },
        "prime_work": {
            **_stats(values(rows, "prepared_prime_seconds")),
            "total": sum(values(rows, "prepared_prime_seconds")),
        },
        "prompt_tokens": _stats(values(rows, "prompt_tokens")),
        "response_tokens": _stats(values(rows, "response_tokens")),
    }

    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ensure_ollama_model_loaded(LLM_MODEL)

    recent = ShortTermMemory(max_turns=1)
    recall = SessionArchive(max_turns=384)
    profile = ProfileFactIndex(
        {
            "name": "Anders",
            "vehicle": "black Jeep",
            "project": "NANCEE",
        }
    )

    tpc = None
    next_prepared_prime_result = None

    if args.mode == "tpc":
        tpc = create_ollama_tpc()
        next_prepared_prime_result = tpc.prime_now(
            history=[],
            memory_context="",
            reason="benchmark_startup",
        )

    rows: list[dict[str, object]] = []

    try:
        for index, case in enumerate(CASES, start=1):
            if index > 1 and args.interturn_seconds > 0:
                time.sleep(args.interturn_seconds)

            previous_turns = recent.get_turns_snapshot()
            previous_turn = previous_turns[-1] if previous_turns else None

            if case.previous_assistant is not None:
                previous_turn = {
                    "user": "benchmark setup",
                    "assistant": case.previous_assistant,
                }

            route_started = time.perf_counter()
            route = route_user_input(case.text, previous_turn=previous_turn)
            route_seconds = time.perf_counter() - route_started

            if route.kind != case.expected_route:
                raise RuntimeError(
                    f"Route mismatch at {index}: {case.label}: "
                    f"expected={case.expected_route} actual={route.kind}"
                )

            profile_context, profile_hits = profile.retrieve_context(case.text)
            profile_found = bool(profile_context.strip())

            if profile_found:
                retrieved_context = ""
                memory_found = False
            elif route.retrieve_recall:
                retrieved_context = retrieve_context(
                    recall,
                    case.text,
                    allow_weak_match=route.allow_weak_match,
                )
                memory_found = bool(retrieved_context.strip())
            else:
                retrieved_context = ""
                memory_found = False

            fact_miss = route.explicit_recall and not profile_found and not memory_found

            if fact_miss:
                profile_context = (
                    "No matching confirmed fact about the human user was retrieved. "
                    "Say only that you do not remember it yet."
                )

            authoritative_found = profile_found or (route.explicit_recall and memory_found)
            authoritative_required = authoritative_found or fact_miss

            policy = response_policy_for_route(
                route.kind,
                authoritative_context_found=authoritative_found,
                fact_miss=fact_miss,
            )

            if route.force_keep_history:
                request_history = recent.get_messages()
            elif authoritative_required or policy.drop_history:
                request_history = []
            else:
                request_history = recent.get_messages()

            live_history = recent.get_messages()
            require_exact = request_history == live_history and not profile_context.strip()

            tpc_wait_seconds = 0.0
            prepared_prime_seconds = 0.0

            if tpc is not None:
                if next_prepared_prime_result is not None:
                    prepared_prime_seconds = float(
                        next_prepared_prime_result.get("elapsed_seconds", 0.0)
                    )
                    next_prepared_prime_result = None

                wait_started = time.perf_counter()
                waited_result = tpc.wait_until_ready()
                tpc_wait_seconds = time.perf_counter() - wait_started

                if waited_result is not None:
                    prepared_prime_seconds = float(
                        waited_result.get("elapsed_seconds", 0.0)
                    )

            completion_state: dict[str, object] = {}

            request_kwargs = dict(
                user_text=case.text,
                history=request_history,
                memory_context=profile_context,
                retrieved_context=retrieved_context,
                response_instruction=policy.instruction,
                temperature=args.temperature,
                num_predict=args.num_predict,
                completion_state=completion_state,
            )

            request_started = time.perf_counter()

            if tpc is not None:
                token_iterator = tpc.stream_response(
                    require_exact_prefix=require_exact,
                    **request_kwargs,
                )
            else:
                token_iterator = stream_ollama_response(**request_kwargs)

            response_parts = list(token_iterator)
            external_total_seconds = time.perf_counter() - request_started
            response_text = "".join(response_parts).strip() or "(empty)"

            if route.store_recall:
                recall.add_turn(route.recall_storage_text or case.text)

            recent.add_turn(case.text, response_text)

            if tpc is not None:
                tpc.prime_async(
                    history=recent.get_messages(),
                    memory_context="",
                    reason="benchmark_completed_turn",
                )

            row = {
                "mode": args.mode,
                "index": index,
                "label": case.label,
                "question": case.text,
                "route": route.kind,
                "exact_prefix_required": require_exact,
                "route_seconds": route_seconds,
                "tpc_wait_seconds": tpc_wait_seconds,
                "prepared_prime_seconds": prepared_prime_seconds,
                "first_token_seconds": float(completion_state.get("first_token_seconds") or 0.0),
                "foreground_first_token_seconds": (
                    tpc_wait_seconds
                    + float(completion_state.get("first_token_seconds") or 0.0)
                ),
                "prompt_eval_seconds": float(completion_state.get("prompt_eval_seconds") or 0.0),
                "generation_seconds": float(completion_state.get("generation_seconds") or 0.0),
                "request_total_seconds": float(completion_state.get("total_seconds") or external_total_seconds),
                "foreground_total_seconds": (
                    tpc_wait_seconds
                    + float(completion_state.get("total_seconds") or external_total_seconds)
                ),
                "external_total_seconds": external_total_seconds,
                "prompt_tokens": int(completion_state.get("prompt_tokens") or 0),
                "response_tokens": int(completion_state.get("response_tokens") or 0),
                "response_chars": len(response_text),
            }
            rows.append(row)

            print(
                "[BENCH TURN] "
                f"mode={args.mode} index={index:02d} route={route.kind} "
                f"route_time={row['route_seconds']:.4f}s "
                f"first_token={row['first_token_seconds']:.3f}s "
                f"foreground_first={row['foreground_first_token_seconds']:.3f}s "
                f"prompt_eval={row['prompt_eval_seconds']:.3f}s "
                f"foreground_total={row['foreground_total_seconds']:.3f}s "
                f"tpc_wait={tpc_wait_seconds:.3f}s",
                flush=True,
            )

    finally:
        if tpc is not None:
            tpc.shutdown()

    fieldnames = list(rows[0].keys())

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary_path = output_path.with_suffix(".summary.json")
    write_summary(summary_path, mode=args.mode, rows=rows)

    print(f"[BENCH OUTPUT] csv={output_path}")
    print(f"[BENCH OUTPUT] summary={summary_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark NANCEE routing with and without TPC across 30 fixed prompts."
    )
    parser.add_argument("--mode", choices=("tpc", "no-tpc"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--interturn-seconds",
        type=float,
        default=4.5,
        help="Simulated user/ASR time available for an async prime. Default: 4.5",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Use zero for repeatable latency comparison. Default: 0.0",
    )
    parser.add_argument(
        "--num-predict",
        type=int,
        default=12,
        help="Fixed response-token cap to reduce output-length noise. Default: 12",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
