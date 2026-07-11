#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SHERPA = ROOT / "sherpa"
sys.path.insert(0, str(SHERPA))

from config import (  # noqa: E402
    LLM_MODEL,
    LLM_NUM_THREADS,
    OLLAMA_RESPONSE_TIMEOUT,
    OLLAMA_URL,
    load_system_prompt,
)
from session_archive import SessionArchive  # noqa: E402
from user_profile import UserProfile  # noqa: E402


@dataclass(frozen=True)
class BenchCase:
    case_id: str
    user_text: str
    stored_texts: tuple[str, ...] = ()
    expected_all: tuple[str, ...] = ()
    expected_any: tuple[str, ...] = ()
    forbidden_any: tuple[str, ...] = ()
    expect_unknown: bool = False
    max_words: int = 24
    kind: str = "llm"


UNKNOWN_MARKERS = (
    "do not remember",
    "don't remember",
    "do not know",
    "don't know",
    "not know",
    "no memory",
    "not in my memory",
    "i don't have",
    "i do not have",
    "not enough information",
)

COLOR_WORDS = (
    "red",
    "blue",
    "green",
    "yellow",
    "purple",
    "orange",
    "black",
    "white",
)

RAMBLE_MARKERS = (
    "how can i assist",
    "what did you buy",
    "what kind of",
    "craving",
    "phone's parking app",
    "gps history",
    "outside my expertise",
    "vehicle maintenance",
    "as an ai",
    "i'm sorry for the inconvenience",
    "please provide",
)


CASES = [
    BenchCase(
        case_id="normal_buy_statement",
        user_text="I bought Japanese candy at Ocean Market.",
        expected_any=("got it", "okay", "remember", "japanese", "candy"),
        forbidden_any=("what did you buy", "what kind of", "craving", "outside my expertise"),
        max_words=18,
        kind="normal",
    ),
    BenchCase(
        case_id="normal_park_statement",
        user_text="I parked on level 3 near the west elevator.",
        expected_any=("got it", "okay", "level", "west", "elevator"),
        forbidden_any=("phone", "gps", "parking app", "where did you park"),
        max_words=18,
        kind="normal",
    ),
    BenchCase(
        case_id="fts_buy_recall",
        user_text="What did I buy at Ocean Market?",
        stored_texts=("I bought Japanese candy at Ocean Market.",),
        expected_all=("japanese", "candy"),
        forbidden_any=("hot sauce", "ramen", "soda", "horse exercise"),
        max_words=18,
        kind="recall",
    ),
    BenchCase(
        case_id="fts_park_recall",
        user_text="Where did I park?",
        stored_texts=("I parked on level 3 near the west elevator.",),
        expected_any=("level 3", "level three"),
        expected_all=("west", "elevator"),
        forbidden_any=("phone", "gps", "parking app"),
        max_words=20,
        kind="recall",
    ),
    BenchCase(
        case_id="unknown_favorite_color",
        user_text="What is my favorite color?",
        expect_unknown=True,
        forbidden_any=COLOR_WORDS,
        max_words=20,
        kind="unknown",
    ),
    BenchCase(
        case_id="unknown_passport",
        user_text="Where did I put my passport?",
        expect_unknown=True,
        forbidden_any=("drawer", "desk", "bag", "glove box", "car", "jeep"),
        max_words=20,
        kind="unknown",
    ),
    BenchCase(
        case_id="junk_statement_in_my_name",
        user_text="In my name.",
        expected_any=("don't", "do not", "not", "unclear", "okay", "got it"),
        forbidden_any=("phone", "gps", "parking app", "west elevator", "black jeep"),
        max_words=18,
        kind="junk",
    ),
]


DIRECT_PROFILE_CASES = [
    ("direct_name", "What is my name?", "Your name is Anders."),
    ("direct_vehicle", "What vehicle do I have?", "You drive a black Jeep."),
    ("direct_unknown_color", "What is my favorite color?", ""),
]


def parse_csv_numbers(value: str, cast):
    return [cast(part.strip()) for part in value.split(",") if part.strip()]


def ns_to_s(value: Any) -> float:
    try:
        return float(value or 0) / 1_000_000_000
    except (TypeError, ValueError):
        return 0.0


def word_count(text: str) -> int:
    return len(str(text).split())


def profile_context(max_chars: int) -> str:
    if max_chars <= 0:
        return ""

    profile = UserProfile(
        {
            "name": "Anders",
            "vehicle": "black Jeep",
            "project": "NANCEE in-car OBD assistant",
        }
    )

    return profile.format_context(max_characters=max_chars)


def recent_messages(turns: int) -> list[dict[str, str]]:
    if turns <= 0:
        return []

    base = [
        {
            "role": "user",
            "content": "What vehicle do I drive?",
        },
        {
            "role": "assistant",
            "content": "You drive a black Jeep.",
        },
    ]

    if turns == 1:
        return base

    messages = []

    for index in range(turns):
        messages.extend(
            [
                {
                    "role": "user",
                    "content": f"Recent user turn {index}.",
                },
                {
                    "role": "assistant",
                    "content": "Okay.",
                },
            ]
        )

    return messages


def make_retrieved_context(
    case: BenchCase,
    recall_limit: int,
    recall_chars: int,
) -> tuple[str, int, float, float]:
    if not case.stored_texts:
        return "", 0, 0.0, 0.0

    archive = SessionArchive(max_turns=384)

    add_started = time.perf_counter()

    for stored in case.stored_texts:
        archive.add_turn(stored, "Okay.")

    add_elapsed = time.perf_counter() - add_started

    retrieve_started = time.perf_counter()

    hits = archive.retrieve(
        case.user_text,
        limit=recall_limit,
    )

    retrieved_context = archive.format_related_context(
        hits,
        max_characters=recall_chars,
    )

    retrieve_elapsed = time.perf_counter() - retrieve_started

    return retrieved_context, len(hits), add_elapsed, retrieve_elapsed


def build_messages(
    *,
    system_prompt: str,
    user_text: str,
    profile: str,
    retrieved_context: str,
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    if profile.strip():
        messages.append(
            {
                "role": "system",
                "content": profile.strip(),
            }
        )

    messages.extend(history)

    if retrieved_context.strip():
        messages.append(
            {
                "role": "system",
                "content": (
                    "Use the relevant user memory below to answer the user's question. "
                    "In memory lines, I, me, and my refer to the human user, not Nancee. "
                    "Do not guess.\n\n"
                    f"{retrieved_context.strip()}"
                ),
            }
        )

    messages.append(
        {
            "role": "user",
            "content": user_text.strip(),
        }
    )

    return messages


def call_ollama_stream(
    *,
    model: str,
    url: str,
    messages: list[dict[str, str]],
    temperature: float,
    num_predict: int,
    num_threads: int,
    timeout: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "stream": True,
        "keep_alive": -1,
        "messages": messages,
        "options": {
            "temperature": temperature,
            "num_thread": num_threads,
            "num_predict": num_predict,
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    started = time.perf_counter()
    first_token_s = None
    chunks: list[str] = []
    final: dict[str, Any] = {}

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            for raw_line in response:
                line = raw_line.decode(
                    "utf-8",
                    errors="replace",
                ).strip()

                if not line:
                    continue

                data = json.loads(line)

                if data.get("error"):
                    raise RuntimeError(data["error"])

                token = data.get("message", {}).get("content", "")

                if token:
                    if first_token_s is None:
                        first_token_s = time.perf_counter() - started

                    chunks.append(token)

                if data.get("done"):
                    final = data
                    break

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        RuntimeError,
    ) as error:
        return {
            "ok": False,
            "error": repr(error),
            "wall_s": time.perf_counter() - started,
            "first_token_s": first_token_s,
            "response_text": "".join(chunks).strip(),
        }

    wall_s = time.perf_counter() - started

    return {
        "ok": True,
        "error": "",
        "wall_s": wall_s,
        "first_token_s": first_token_s if first_token_s is not None else wall_s,
        "response_text": "".join(chunks).strip(),
        "done_reason": final.get("done_reason", ""),
        "load_s": ns_to_s(final.get("load_duration")),
        "prompt_eval_s": ns_to_s(final.get("prompt_eval_duration")),
        "generation_s": ns_to_s(final.get("eval_duration")),
        "prompt_tokens": final.get("prompt_eval_count", 0),
        "response_tokens": final.get("eval_count", 0),
    }


def score_case(case: BenchCase, response: str, done_reason: str) -> tuple[int, str]:
    text = response.lower()
    score = 100
    reasons = []

    if not response.strip():
        score -= 80
        reasons.append("empty_response")

    if done_reason == "length":
        score -= 35
        reasons.append("hit_length_limit")

    words = word_count(response)

    if words > case.max_words:
        score -= min(40, (words - case.max_words) * 3)
        reasons.append(f"too_long_words={words}")

    for term in case.expected_all:
        if term.lower() not in text:
            score -= 30
            reasons.append(f"missing_required={term}")

    if case.expected_any:
        if not any(term.lower() in text for term in case.expected_any):
            score -= 25
            reasons.append("missing_any_expected")

    if case.expect_unknown:
        if not any(marker in text for marker in UNKNOWN_MARKERS):
            score -= 40
            reasons.append("did_not_admit_unknown")

    for term in case.forbidden_any:
        if term.lower() in text:
            score -= 35
            reasons.append(f"forbidden={term}")

    for marker in RAMBLE_MARKERS:
        if marker in text:
            score -= 20
            reasons.append(f"ramble_marker={marker}")

    score = max(0, min(100, score))

    return score, "|".join(reasons)


def write_row(writer, row: dict[str, Any]) -> None:
    writer.writerow(row)


def aggregate(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}

    for row in rows:
        key = tuple(row[field] for field in group_fields)
        groups.setdefault(key, []).append(row)

    summary = []

    for key, group_rows in groups.items():
        scores = [float(row["score"]) for row in group_rows]
        wall = [float(row["wall_s"]) for row in group_rows]
        first = [float(row["first_token_s"]) for row in group_rows]
        prompt = [float(row["prompt_eval_s"]) for row in group_rows]
        generation = [float(row["generation_s"]) for row in group_rows]
        length_rate = sum(1 for row in group_rows if row["done_reason"] == "length") / len(group_rows)

        item = {
            field: value
            for field, value in zip(group_fields, key)
        }

        item.update(
            {
                "count": len(group_rows),
                "avg_score": round(statistics.mean(scores), 3),
                "min_score": round(min(scores), 3),
                "avg_wall_s": round(statistics.mean(wall), 3),
                "p50_wall_s": round(statistics.median(wall), 3),
                "avg_first_token_s": round(statistics.mean(first), 3),
                "avg_prompt_eval_s": round(statistics.mean(prompt), 3),
                "avg_generation_s": round(statistics.mean(generation), 3),
                "length_rate": round(length_rate, 3),
            }
        )

        summary.append(item)

    summary.sort(
        key=lambda row: (
            -row["avg_score"],
            row["length_rate"],
            row["avg_wall_s"],
            row["avg_first_token_s"],
        )
    )

    return summary


def run_direct_profile_bench(output_dir: Path) -> None:
    profile = UserProfile(
        {
            "name": "Anders",
            "vehicle": "black Jeep",
            "project": "NANCEE in-car OBD assistant",
        }
    )

    path = output_dir / "direct_profile.csv"

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "case_id",
                "user_text",
                "expected",
                "actual",
                "ok",
                "elapsed_s",
            ],
        )

        writer.writeheader()

        for case_id, user_text, expected in DIRECT_PROFILE_CASES:
            started = time.perf_counter()
            actual = profile.direct_answer(user_text)
            elapsed = time.perf_counter() - started

            writer.writerow(
                {
                    "case_id": case_id,
                    "user_text": user_text,
                    "expected": expected,
                    "actual": actual,
                    "ok": actual == expected,
                    "elapsed_s": f"{elapsed:.9f}",
                }
            )

    print(f"[DIRECT PROFILE] wrote={path}")


def run_storage_microbench(output_dir: Path, memory_count: int, repeat: int) -> None:
    path = output_dir / "storage_retrieval_microbench.csv"

    queries = [
        "What did I buy at Ocean Market?",
        "Where did I park?",
        "Where is the OBD cable?",
        "Where did I buy hot sauce?",
    ]

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "repeat",
                "memory_count",
                "add_total_s",
                "add_avg_ms",
                "query",
                "hits",
                "retrieve_s",
                "retrieve_ms",
                "context_chars",
            ],
        )

        writer.writeheader()

        for r in range(repeat):
            archive = SessionArchive(max_turns=memory_count)

            base_items = [
                "I bought Japanese candy at Ocean Market.",
                "I parked on level 3 near the west elevator.",
                "I keep the OBD cable in the glove box.",
                "I bought hot sauce at Ocean Market.",
            ]

            filler = [
                f"Filler memory number {index} about routine driving note {index}."
                for index in range(memory_count)
            ]

            started = time.perf_counter()

            for item in base_items + filler:
                archive.add_turn(item, "Okay.")

            add_total = time.perf_counter() - started
            add_avg_ms = (add_total / max(1, memory_count + len(base_items))) * 1000

            for query in queries:
                retrieve_started = time.perf_counter()
                hits = archive.retrieve(query, limit=3)
                context = archive.format_related_context(hits, max_characters=650)
                retrieve_s = time.perf_counter() - retrieve_started

                writer.writerow(
                    {
                        "repeat": r,
                        "memory_count": memory_count,
                        "add_total_s": f"{add_total:.9f}",
                        "add_avg_ms": f"{add_avg_ms:.6f}",
                        "query": query,
                        "hits": len(hits),
                        "retrieve_s": f"{retrieve_s:.9f}",
                        "retrieve_ms": f"{retrieve_s * 1000:.6f}",
                        "context_chars": len(context),
                    }
                )

    print(f"[STORAGE] wrote={path}")


def run_prime_shape_probe(
    *,
    output_dir: Path,
    model: str,
    url: str,
    system_prompt: str,
    temperature: float,
    num_threads: int,
    timeout: int,
    repeat: int,
) -> None:
    path = output_dir / "prime_prompt_shape_probe.csv"

    shapes = [
        {
            "shape_id": "system_only_startup_prime",
            "profile_chars": 0,
            "retrieved_context": "",
            "history": [],
        },
        {
            "shape_id": "profile_only",
            "profile_chars": 650,
            "retrieved_context": "",
            "history": [],
        },
        {
            "shape_id": "profile_plus_recent",
            "profile_chars": 650,
            "retrieved_context": "",
            "history": recent_messages(1),
        },
        {
            "shape_id": "profile_plus_retrieved",
            "profile_chars": 650,
            "retrieved_context": (
                "RELEVANT USER MEMORY:\n"
                "USER MEMORY QUOTES:\n"
                '- Human user said: "I bought Japanese candy at Ocean Market."'
            ),
            "history": [],
        },
        {
            "shape_id": "profile_plus_recent_plus_retrieved",
            "profile_chars": 650,
            "retrieved_context": (
                "RELEVANT USER MEMORY:\n"
                "USER MEMORY QUOTES:\n"
                '- Human user said: "I parked on level 3 near the west elevator."'
            ),
            "history": recent_messages(1),
        },
    ]

    with path.open("w", newline="", encoding="utf-8") as file:
        fieldnames = [
            "repeat",
            "shape_id",
            "messages",
            "history_messages",
            "profile_chars",
            "retrieved_context_chars",
            "ok",
            "error",
            "wall_s",
            "first_token_s",
            "prompt_eval_s",
            "generation_s",
            "prompt_tokens",
            "response_tokens",
            "done_reason",
        ]

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for r in range(repeat):
            for shape in shapes:
                profile = profile_context(shape["profile_chars"])

                messages = build_messages(
                    system_prompt=system_prompt,
                    user_text="Internal context preparation. Reply READY only.",
                    profile=profile,
                    retrieved_context=shape["retrieved_context"],
                    history=shape["history"],
                )

                result = call_ollama_stream(
                    model=model,
                    url=url,
                    messages=messages,
                    temperature=temperature,
                    num_predict=1,
                    num_threads=num_threads,
                    timeout=timeout,
                )

                writer.writerow(
                    {
                        "repeat": r,
                        "shape_id": shape["shape_id"],
                        "messages": len(messages),
                        "history_messages": len(shape["history"]),
                        "profile_chars": len(profile),
                        "retrieved_context_chars": len(shape["retrieved_context"]),
                        "ok": result.get("ok"),
                        "error": result.get("error", ""),
                        "wall_s": result.get("wall_s", 0),
                        "first_token_s": result.get("first_token_s", 0),
                        "prompt_eval_s": result.get("prompt_eval_s", 0),
                        "generation_s": result.get("generation_s", 0),
                        "prompt_tokens": result.get("prompt_tokens", 0),
                        "response_tokens": result.get("response_tokens", 0),
                        "done_reason": result.get("done_reason", ""),
                    }
                )

                file.flush()

    print(f"[PRIME SHAPES] wrote={path}")


def run_matrix(
    *,
    output_dir: Path,
    model: str,
    url: str,
    system_prompt: str,
    temps: list[float],
    num_predicts: list[int],
    recent_turn_values: list[int],
    recall_limits: list[int],
    recall_chars_values: list[int],
    profile_chars_values: list[int],
    num_threads: int,
    timeout: int,
    max_requests: int | None,
) -> list[dict[str, Any]]:
    path = output_dir / "runtime_config_matrix.csv"

    fieldnames = [
        "stage",
        "case_id",
        "case_kind",
        "temperature",
        "num_predict",
        "recent_turns",
        "recall_limit",
        "recall_context_chars_setting",
        "profile_context_chars_setting",
        "messages",
        "history_messages",
        "profile_context_chars",
        "retrieved_context_chars",
        "retrieval_hits",
        "storage_add_s",
        "retrieval_s",
        "ok",
        "error",
        "score",
        "score_reasons",
        "wall_s",
        "first_token_s",
        "load_s",
        "prompt_eval_s",
        "generation_s",
        "prompt_tokens",
        "response_tokens",
        "done_reason",
        "response_text",
    ]

    rows: list[dict[str, Any]] = []
    request_count = 0

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        # Stage 1: LLM behavior sweep. Fixed memory settings.
        for temperature in temps:
            for num_predict in num_predicts:
                for recent_turns in recent_turn_values:
                    for case in CASES:
                        if max_requests is not None and request_count >= max_requests:
                            print("[MATRIX] max_requests reached")
                            return rows

                        prof = profile_context(650)
                        history = recent_messages(recent_turns)

                        retrieved, hits, add_s, ret_s = make_retrieved_context(
                            case,
                            recall_limit=3,
                            recall_chars=500,
                        )

                        # Recall turns intentionally do not get active history.
                        if case.kind == "recall":
                            history = []

                        messages = build_messages(
                            system_prompt=system_prompt,
                            user_text=case.user_text,
                            profile=prof,
                            retrieved_context=retrieved,
                            history=history,
                        )

                        result = call_ollama_stream(
                            model=model,
                            url=url,
                            messages=messages,
                            temperature=temperature,
                            num_predict=num_predict,
                            num_threads=num_threads,
                            timeout=timeout,
                        )

                        score, reasons = score_case(
                            case,
                            result.get("response_text", ""),
                            result.get("done_reason", ""),
                        )

                        row = {
                            "stage": "stage1_llm_temp_predict_recent",
                            "case_id": case.case_id,
                            "case_kind": case.kind,
                            "temperature": temperature,
                            "num_predict": num_predict,
                            "recent_turns": recent_turns,
                            "recall_limit": 3,
                            "recall_context_chars_setting": 500,
                            "profile_context_chars_setting": 650,
                            "messages": len(messages),
                            "history_messages": len(history),
                            "profile_context_chars": len(prof),
                            "retrieved_context_chars": len(retrieved),
                            "retrieval_hits": hits,
                            "storage_add_s": f"{add_s:.9f}",
                            "retrieval_s": f"{ret_s:.9f}",
                            "ok": result.get("ok"),
                            "error": result.get("error", ""),
                            "score": score,
                            "score_reasons": reasons,
                            "wall_s": result.get("wall_s", 0),
                            "first_token_s": result.get("first_token_s", 0),
                            "load_s": result.get("load_s", 0),
                            "prompt_eval_s": result.get("prompt_eval_s", 0),
                            "generation_s": result.get("generation_s", 0),
                            "prompt_tokens": result.get("prompt_tokens", 0),
                            "response_tokens": result.get("response_tokens", 0),
                            "done_reason": result.get("done_reason", ""),
                            "response_text": result.get("response_text", "").replace("\n", "\\n"),
                        }

                        write_row(writer, row)
                        rows.append(row)
                        request_count += 1
                        file.flush()

                        print(
                            "[MATRIX] "
                            f"{request_count} "
                            f"stage1 "
                            f"temp={temperature} "
                            f"predict={num_predict} "
                            f"recent={recent_turns} "
                            f"case={case.case_id} "
                            f"score={score} "
                            f"wall={float(row['wall_s']):.2f}s "
                            f"done={row['done_reason']}",
                            flush=True,
                        )

        # Pick best stage 1 combo for memory-shape sweep.
        stage1_summary = aggregate(
            [
                row
                for row in rows
                if row["stage"] == "stage1_llm_temp_predict_recent"
            ],
            ("temperature", "num_predict", "recent_turns"),
        )

        if stage1_summary:
            best = stage1_summary[0]
            best_temp = float(best["temperature"])
            best_predict = int(best["num_predict"])
            best_recent = int(best["recent_turns"])
        else:
            best_temp = 0.3
            best_predict = 32
            best_recent = 1

        print(
            "[MATRIX] stage2 using best stage1 "
            f"temperature={best_temp} "
            f"num_predict={best_predict} "
            f"recent_turns={best_recent}",
            flush=True,
        )

        memory_cases = [
            case
            for case in CASES
            if case.kind in {"recall", "unknown"}
        ]

        # Stage 2: memory/profile context shape sweep.
        for recall_limit in recall_limits:
            for recall_chars in recall_chars_values:
                for prof_chars in profile_chars_values:
                    for case in memory_cases:
                        if max_requests is not None and request_count >= max_requests:
                            print("[MATRIX] max_requests reached")
                            return rows

                        prof = profile_context(prof_chars)
                        history = [] if case.kind == "recall" else recent_messages(best_recent)

                        retrieved, hits, add_s, ret_s = make_retrieved_context(
                            case,
                            recall_limit=recall_limit,
                            recall_chars=recall_chars,
                        )

                        messages = build_messages(
                            system_prompt=system_prompt,
                            user_text=case.user_text,
                            profile=prof,
                            retrieved_context=retrieved,
                            history=history,
                        )

                        result = call_ollama_stream(
                            model=model,
                            url=url,
                            messages=messages,
                            temperature=best_temp,
                            num_predict=best_predict,
                            num_threads=num_threads,
                            timeout=timeout,
                        )

                        score, reasons = score_case(
                            case,
                            result.get("response_text", ""),
                            result.get("done_reason", ""),
                        )

                        row = {
                            "stage": "stage2_memory_shape",
                            "case_id": case.case_id,
                            "case_kind": case.kind,
                            "temperature": best_temp,
                            "num_predict": best_predict,
                            "recent_turns": best_recent,
                            "recall_limit": recall_limit,
                            "recall_context_chars_setting": recall_chars,
                            "profile_context_chars_setting": prof_chars,
                            "messages": len(messages),
                            "history_messages": len(history),
                            "profile_context_chars": len(prof),
                            "retrieved_context_chars": len(retrieved),
                            "retrieval_hits": hits,
                            "storage_add_s": f"{add_s:.9f}",
                            "retrieval_s": f"{ret_s:.9f}",
                            "ok": result.get("ok"),
                            "error": result.get("error", ""),
                            "score": score,
                            "score_reasons": reasons,
                            "wall_s": result.get("wall_s", 0),
                            "first_token_s": result.get("first_token_s", 0),
                            "load_s": result.get("load_s", 0),
                            "prompt_eval_s": result.get("prompt_eval_s", 0),
                            "generation_s": result.get("generation_s", 0),
                            "prompt_tokens": result.get("prompt_tokens", 0),
                            "response_tokens": result.get("response_tokens", 0),
                            "done_reason": result.get("done_reason", ""),
                            "response_text": result.get("response_text", "").replace("\n", "\\n"),
                        }

                        write_row(writer, row)
                        rows.append(row)
                        request_count += 1
                        file.flush()

                        print(
                            "[MATRIX] "
                            f"{request_count} "
                            f"stage2 "
                            f"limit={recall_limit} "
                            f"recall_chars={recall_chars} "
                            f"profile_chars={prof_chars} "
                            f"case={case.case_id} "
                            f"score={score} "
                            f"wall={float(row['wall_s']):.2f}s "
                            f"done={row['done_reason']}",
                            flush=True,
                        )

    print(f"[MATRIX] wrote={path}")
    return rows


def write_summaries(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    summary_path = output_dir / "summary_top_configs.json"

    summaries = {
        "stage1_by_temp_predict_recent": aggregate(
            [
                row
                for row in rows
                if row["stage"] == "stage1_llm_temp_predict_recent"
            ],
            ("temperature", "num_predict", "recent_turns"),
        )[:25],
        "stage2_by_memory_shape": aggregate(
            [
                row
                for row in rows
                if row["stage"] == "stage2_memory_shape"
            ],
            (
                "recall_limit",
                "recall_context_chars_setting",
                "profile_context_chars_setting",
            ),
        )[:25],
        "case_summary": aggregate(
            rows,
            ("case_id",),
        ),
    }

    summary_path.write_text(
        json.dumps(
            summaries,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    md_path = output_dir / "summary_top_configs.md"

    lines = [
        "# NANCEE runtime config benchmark summary",
        "",
        "## Stage 1: temperature / num_predict / recent turns",
        "",
    ]

    for row in summaries["stage1_by_temp_predict_recent"][:10]:
        lines.append(
            "- "
            f"temp={row['temperature']} "
            f"num_predict={row['num_predict']} "
            f"recent_turns={row['recent_turns']} "
            f"avg_score={row['avg_score']} "
            f"length_rate={row['length_rate']} "
            f"avg_wall_s={row['avg_wall_s']} "
            f"avg_prompt_eval_s={row['avg_prompt_eval_s']} "
            f"avg_generation_s={row['avg_generation_s']}"
        )

    lines.extend(
        [
            "",
            "## Stage 2: memory/profile shape",
            "",
        ]
    )

    for row in summaries["stage2_by_memory_shape"][:10]:
        lines.append(
            "- "
            f"recall_limit={row['recall_limit']} "
            f"recall_chars={row['recall_context_chars_setting']} "
            f"profile_chars={row['profile_context_chars_setting']} "
            f"avg_score={row['avg_score']} "
            f"length_rate={row['length_rate']} "
            f"avg_wall_s={row['avg_wall_s']} "
            f"avg_prompt_eval_s={row['avg_prompt_eval_s']} "
            f"avg_generation_s={row['avg_generation_s']}"
        )

    lines.extend(
        [
            "",
            "## Case-level weak spots",
            "",
        ]
    )

    for row in summaries["case_summary"]:
        lines.append(
            "- "
            f"{row['case_id']}: "
            f"avg_score={row['avg_score']} "
            f"min_score={row['min_score']} "
            f"length_rate={row['length_rate']} "
            f"avg_wall_s={row['avg_wall_s']}"
        )

    md_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(f"[SUMMARY] wrote={summary_path}")
    print(f"[SUMMARY] wrote={md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark NANCEE runtime config tunables against Ollama."
    )

    parser.add_argument(
        "--mode",
        choices=("quick", "night"),
        default="night",
    )

    parser.add_argument(
        "--model",
        default=os.getenv("LLM_MODEL", LLM_MODEL),
    )

    parser.add_argument(
        "--url",
        default=os.getenv("OLLAMA_URL", OLLAMA_URL),
    )

    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "test" / "benchmark" / "results"),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=OLLAMA_RESPONSE_TIMEOUT,
    )

    parser.add_argument(
        "--num-threads",
        type=int,
        default=LLM_NUM_THREADS,
    )

    parser.add_argument(
        "--max-requests",
        type=int,
        default=0,
        help="0 means no cap.",
    )

    parser.add_argument(
        "--storage-memory-count",
        type=int,
        default=384,
    )

    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / f"runtime_config_{args.mode}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[OUTPUT] {output_dir}")
    print(f"[MODEL] {args.model}")
    print(f"[URL] {args.url}")
    print(f"[MODE] {args.mode}")

    if args.mode == "quick":
        temps = [0.0, 0.3]
        num_predicts = [20, 32]
        recent_turn_values = [0, 1]
        recall_limits = [1, 3]
        recall_chars_values = [350, 650]
        profile_chars_values = [0, 650]
        prime_repeat = 2
        storage_repeat = 5

    else:
        temps = [0.0, 0.1, 0.2, 0.3, 0.4, 0.6]
        num_predicts = [12, 16, 20, 24, 28, 32, 40]
        recent_turn_values = [0, 1]
        recall_limits = [1, 2, 3]
        recall_chars_values = [220, 350, 500, 650]
        profile_chars_values = [0, 300, 650, 1000]
        prime_repeat = 5
        storage_repeat = 20

    max_requests = args.max_requests if args.max_requests > 0 else None

    system_prompt = load_system_prompt()

    run_direct_profile_bench(output_dir)

    run_storage_microbench(
        output_dir=output_dir,
        memory_count=args.storage_memory_count,
        repeat=storage_repeat,
    )

    run_prime_shape_probe(
        output_dir=output_dir,
        model=args.model,
        url=args.url,
        system_prompt=system_prompt,
        temperature=0.0,
        num_threads=args.num_threads,
        timeout=args.timeout,
        repeat=prime_repeat,
    )

    rows = run_matrix(
        output_dir=output_dir,
        model=args.model,
        url=args.url,
        system_prompt=system_prompt,
        temps=temps,
        num_predicts=num_predicts,
        recent_turn_values=recent_turn_values,
        recall_limits=recall_limits,
        recall_chars_values=recall_chars_values,
        profile_chars_values=profile_chars_values,
        num_threads=args.num_threads,
        timeout=args.timeout,
        max_requests=max_requests,
    )

    write_summaries(output_dir, rows)

    print()
    print("[DONE]")
    print(f"Results directory: {output_dir}")
    print(f"Main CSV: {output_dir / 'runtime_config_matrix.csv'}")
    print(f"Summary: {output_dir / 'summary_top_configs.md'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
