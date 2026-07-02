#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SHERPA_DIRECTORY = REPOSITORY_ROOT / "sherpa"

sys.path.insert(0, str(SHERPA_DIRECTORY))

from config import (  # noqa: E402
    LLM_MODEL,
    LLM_NUM_THREADS,
    OLLAMA_RESPONSE_TIMEOUT,
    OLLAMA_URL,
    OLLAMA_WARMUP_COMMAND,
)
from ollama_runtime import (  # noqa: E402
    build_ollama_messages,
    prime_ollama_context,
)
from session_archive import (  # noqa: E402
    SessionArchive,
    archive_active_memory_if_needed,
)
from session_fact_extractor import (  # noqa: E402
    promote_archived_facts,
)
from short_term_memory import ShortTermMemory  # noqa: E402

FACT_PROMPT = (
    "My name is Anders. My favorite band is Finch. "
    "They are from Temecula, California. "
    "I drive a 2016 Jeep Patriot and it has code P0420. "
    "Acknowledge this in one short sentence."
)

FILLER_TOPICS = [
    "Give one short sentence about checking tire pressure.",
    "Give one short sentence about keeping a windshield clean.",
    "Give one short sentence about checking engine oil.",
    "Give one short sentence about safe battery inspection.",
    "Give one short sentence about replacing worn wiper blades.",
    "Give one short sentence about listening for unusual noises.",
    "Give one short sentence about checking coolant when the engine is cold.",
    "Give one short sentence about keeping tools secured in a vehicle.",
]

POST_ARCHIVE_CHECKS = [
    ("What is my name? Answer briefly.", "anders"),
    ("Who is my favorite band? Answer briefly.", "finch"),
    (
        "Where did I say Finch is from? Answer briefly.",
        "temecula",
    ),
    ("What vehicle do I drive? Answer briefly.", "jeep patriot"),
    (
        "Which diagnostic code did I mention? Answer briefly.",
        "p0420",
    ),
]


def parse_int_list(value: str) -> list[int]:
    values = []

    for item in value.split(","):
        clean_item = item.strip()

        if not clean_item:
            continue

        number = int(clean_item)

        if number <= 0:
            raise argparse.ArgumentTypeError("All values must be positive integers.")

        values.append(number)

    if not values:
        raise argparse.ArgumentTypeError("At least one integer is required.")

    return values


def duration_seconds(data: dict, field: str) -> float:
    return data.get(field, 0) / 1_000_000_000


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    rank = max(
        1,
        math.ceil((percent / 100.0) * len(ordered)),
    )

    return ordered[rank - 1]


def warm_model(model: str) -> float:
    subprocess.run(
        ["ollama", "stop", model],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(1.0)

    started = time.perf_counter()

    result = subprocess.run(
        [OLLAMA_WARMUP_COMMAND, model],
        check=False,
        capture_output=True,
        text=True,
    )

    elapsed = time.perf_counter() - started

    print("\n--- WARMUP HELPER OUTPUT ---", flush=True)

    if result.stdout:
        print(result.stdout.strip(), flush=True)

    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr, flush=True)

    print("--- END WARMUP HELPER OUTPUT ---\n", flush=True)

    if result.returncode != 0:
        raise RuntimeError(f"Warmup failed with exit code {result.returncode}.")

    return elapsed


def stream_chat_request(
    *,
    user_text: str,
    history: list[dict[str, str]],
    memory_context: str,
    temperature: float,
    num_predict: int,
) -> dict:
    messages = build_ollama_messages(
        user_text=user_text,
        history=history,
        memory_context=memory_context,
        retrieved_context="",
    )

    payload = {
        "model": LLM_MODEL,
        "stream": True,
        "keep_alive": -1,
        "messages": messages,
        "options": {
            "temperature": temperature,
            "num_thread": LLM_NUM_THREADS,
            "num_predict": num_predict,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    started = time.perf_counter()
    first_token_seconds = None
    response_parts: list[str] = []
    final_data = None

    try:
        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_RESPONSE_TIMEOUT,
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
                    raise RuntimeError(f"Ollama returned an error: {data['error']}")

                token = data.get(
                    "message",
                    {},
                ).get(
                    "content",
                    "",
                )

                if token:
                    if first_token_seconds is None:
                        first_token_seconds = time.perf_counter() - started

                    response_parts.append(token)

                if data.get("done"):
                    final_data = data
                    break

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
    ) as error:
        raise RuntimeError(f"Ollama benchmark request failed: {error}") from error

    if final_data is None:
        raise RuntimeError("Ollama benchmark request did not complete.")

    response_text = "".join(response_parts).strip()

    if not response_text:
        raise RuntimeError("Ollama benchmark request returned no text.")

    if first_token_seconds is None:
        raise RuntimeError("Ollama benchmark request had no first token.")

    return {
        "response_text": response_text,
        "first_token_seconds": first_token_seconds,
        "request_seconds": time.perf_counter() - started,
        "load_seconds": duration_seconds(
            final_data,
            "load_duration",
        ),
        "prompt_eval_seconds": duration_seconds(
            final_data,
            "prompt_eval_duration",
        ),
        "generation_seconds": duration_seconds(
            final_data,
            "eval_duration",
        ),
        "prompt_tokens": final_data.get(
            "prompt_eval_count",
            0,
        ),
        "response_tokens": final_data.get(
            "eval_count",
            0,
        ),
    }


def next_pre_archive_prompt(turn_number: int) -> str:
    if turn_number == 1:
        return FACT_PROMPT

    topic = FILLER_TOPICS[(turn_number - 2) % len(FILLER_TOPICS)]

    return f"Benchmark turn {turn_number}. {topic}"


def validate_structured_memory(
    memory: ShortTermMemory,
) -> dict[str, bool]:
    snapshot = memory.snapshot()
    working_state = snapshot["working_state"]
    session_facts = working_state["session_facts"]
    last_dtc_codes = working_state["last_dtc_codes"]

    return {
        "user_name": (session_facts.get("user_name") == "Anders"),
        "favorite_band": (session_facts.get("favorite_band") == "Finch"),
        "favorite_band_origin": (
            session_facts.get("favorite_band_origin") == "Temecula, California"
        ),
        "vehicle": (session_facts.get("vehicle") == "2016 Jeep Patriot"),
        "dtc": ("P0420" in last_dtc_codes),
    }


def run_configuration(
    *,
    character_limit: int,
    keep_recent_turns: int,
    temperature: float,
    num_predict: int,
    max_pre_archive_turns: int,
) -> tuple[list[dict], dict]:
    print()
    print("=" * 78, flush=True)
    print(
        "CONFIG "
        f"character_limit={character_limit} "
        f"keep_recent_turns={keep_recent_turns}",
        flush=True,
    )
    print("=" * 78, flush=True)

    warmup_seconds = warm_model(
        LLM_MODEL,
    )

    memory = ShortTermMemory(
        max_turns=None,
    )
    archive = SessionArchive()

    rows: list[dict] = []
    archive_turn = None
    archived_turn_count = 0
    prime_seconds = 0.0
    promoted_facts: dict = {}

    for turn_number in range(
        1,
        max_pre_archive_turns + 1,
    ):
        user_text = next_pre_archive_prompt(turn_number)

        before_stats = memory.get_stats()

        result = stream_chat_request(
            user_text=user_text,
            history=memory.get_messages(),
            memory_context=memory.build_memory_context(),
            temperature=temperature,
            num_predict=num_predict,
        )

        memory.add_turn(
            user_text=user_text,
            assistant_text=result["response_text"],
        )

        archived_turns = archive_active_memory_if_needed(
            memory=memory,
            archive=archive,
            max_active_turns=9999,
            max_active_characters=character_limit,
            keep_recent_turns=keep_recent_turns,
        )

        after_stats = memory.get_stats()

        rows.append(
            {
                "character_limit": character_limit,
                "keep_recent_turns": keep_recent_turns,
                "phase": "pre_archive",
                "turn": turn_number,
                "active_characters_before": (before_stats["history_characters"]),
                "active_characters_after": (after_stats["history_characters"]),
                "memory_context_characters": (after_stats["memory_context_characters"]),
                "first_token_seconds": round(
                    result["first_token_seconds"],
                    6,
                ),
                "prompt_eval_seconds": round(
                    result["prompt_eval_seconds"],
                    6,
                ),
                "request_seconds": round(
                    result["request_seconds"],
                    6,
                ),
                "prompt_tokens": result["prompt_tokens"],
                "response_tokens": result["response_tokens"],
                "archive_event": bool(archived_turns),
                "memory_check": "",
                "user_text": user_text,
                "response_text": result["response_text"],
            }
        )

        print(
            f"pre turn={turn_number:02d} "
            f"first={result['first_token_seconds']:.3f}s "
            f"prompt_eval={result['prompt_eval_seconds']:.3f}s "
            f"tokens={result['prompt_tokens']} "
            f"active_after={after_stats['history_characters']} "
            f"archive={len(archived_turns)}",
            flush=True,
        )

        if archived_turns:
            archive_turn = turn_number
            archived_turn_count = len(archived_turns)

            promoted_facts = promote_archived_facts(
                memory,
                archived_turns,
            )

            validation = validate_structured_memory(memory)

            print(
                "[STRUCTURED MEMORY VALIDATION] "
                + json.dumps(
                    validation,
                    sort_keys=True,
                ),
                flush=True,
            )
            print(
                "[PROMOTED FACTS] "
                + json.dumps(
                    promoted_facts,
                    sort_keys=True,
                ),
                flush=True,
            )

            prime_result = prime_ollama_context(
                history=memory.get_messages(),
                memory_context=memory.build_memory_context(),
            )

            prime_seconds = float(prime_result["elapsed_seconds"])

            break

    if archive_turn is None:
        raise RuntimeError(
            f"Limit {character_limit} did not archive "
            f"within {max_pre_archive_turns} turns."
        )

    post_rows: list[dict] = []
    memory_checks_passed = 0

    for check_number, (
        user_text,
        expected,
    ) in enumerate(
        POST_ARCHIVE_CHECKS,
        start=1,
    ):
        before_stats = memory.get_stats()

        result = stream_chat_request(
            user_text=user_text,
            history=memory.get_messages(),
            memory_context=memory.build_memory_context(),
            temperature=temperature,
            num_predict=num_predict,
        )

        passed = expected in result["response_text"].lower()

        if passed:
            memory_checks_passed += 1

        memory.add_turn(
            user_text=user_text,
            assistant_text=result["response_text"],
        )

        after_stats = memory.get_stats()

        row = {
            "character_limit": character_limit,
            "keep_recent_turns": keep_recent_turns,
            "phase": "post_archive",
            "turn": check_number,
            "active_characters_before": (before_stats["history_characters"]),
            "active_characters_after": (after_stats["history_characters"]),
            "memory_context_characters": (after_stats["memory_context_characters"]),
            "first_token_seconds": round(
                result["first_token_seconds"],
                6,
            ),
            "prompt_eval_seconds": round(
                result["prompt_eval_seconds"],
                6,
            ),
            "request_seconds": round(
                result["request_seconds"],
                6,
            ),
            "prompt_tokens": result["prompt_tokens"],
            "response_tokens": result["response_tokens"],
            "archive_event": False,
            "memory_check": ("pass" if passed else "fail"),
            "user_text": user_text,
            "response_text": result["response_text"],
        }

        rows.append(row)
        post_rows.append(row)

        print(
            f"post check={check_number:02d} "
            f"first={result['first_token_seconds']:.3f}s "
            f"prompt_eval={result['prompt_eval_seconds']:.3f}s "
            f"tokens={result['prompt_tokens']} "
            f"memory_check={row['memory_check']}",
            flush=True,
        )

    pre_rows = [row for row in rows if row["phase"] == "pre_archive"]

    pre_first_tokens = [float(row["first_token_seconds"]) for row in pre_rows]
    post_first_tokens = [float(row["first_token_seconds"]) for row in post_rows]

    structured_validation = validate_structured_memory(memory)
    structured_checks_passed = sum(
        1 for passed in structured_validation.values() if passed
    )

    amortized_prime_seconds = prime_seconds / archive_turn

    summary = {
        "character_limit": character_limit,
        "keep_recent_turns": keep_recent_turns,
        "warmup_seconds": round(
            warmup_seconds,
            6,
        ),
        "startup_first_token_seconds": round(
            pre_first_tokens[0],
            6,
        ),
        "archive_turn": archive_turn,
        "archived_turn_count": archived_turn_count,
        "prime_seconds": round(
            prime_seconds,
            6,
        ),
        "prime_wait_after_5s": round(
            max(
                0.0,
                prime_seconds - 5.0,
            ),
            6,
        ),
        "prime_wait_after_10s": round(
            max(
                0.0,
                prime_seconds - 10.0,
            ),
            6,
        ),
        "prime_wait_after_15s": round(
            max(
                0.0,
                prime_seconds - 15.0,
            ),
            6,
        ),
        "pre_archive_first_token_median": round(
            statistics.median(
                pre_first_tokens[1:] if len(pre_first_tokens) > 1 else pre_first_tokens
            ),
            6,
        ),
        "pre_archive_first_token_max": round(
            max(pre_first_tokens),
            6,
        ),
        "post_archive_first_token_first": round(
            post_first_tokens[0],
            6,
        ),
        "post_archive_first_token_median": round(
            statistics.median(post_first_tokens),
            6,
        ),
        "post_archive_first_token_p95": round(
            percentile(
                post_first_tokens,
                95.0,
            ),
            6,
        ),
        "amortized_prime_seconds_per_turn": round(
            amortized_prime_seconds,
            6,
        ),
        "structured_checks_passed": (structured_checks_passed),
        "structured_checks_total": len(structured_validation),
        "post_archive_checks_passed": (memory_checks_passed),
        "post_archive_checks_total": len(POST_ARCHIVE_CHECKS),
        "selection_score": round(
            percentile(
                post_first_tokens,
                95.0,
            )
            + amortized_prime_seconds,
            6,
        ),
    }

    print(
        "SUMMARY " + " ".join(f"{key}={value}" for key, value in summary.items()),
        flush=True,
    )

    return rows, summary


def write_csv(
    path: Path,
    rows: list[dict],
) -> None:
    if not rows:
        return

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=list(rows[0].keys()),
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark NANCEE memory limits through one "
            "complete archive, extraction, prime, and recall cycle."
        )
    )

    parser.add_argument(
        "--limits",
        type=parse_int_list,
        default=parse_int_list("1600,2000,2400"),
        help=("Comma-separated active-character limits. Default: 1600,2000,2400"),
    )
    parser.add_argument(
        "--keep-recent",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--num-predict",
        type=int,
        default=32,
    )
    parser.add_argument(
        "--max-pre-archive-turns",
        type=int,
        default=30,
    )

    args = parser.parse_args()

    if args.keep_recent < 0:
        parser.error("--keep-recent cannot be negative.")

    if args.num_predict <= 0:
        parser.error("--num-predict must be positive.")

    if args.max_pre_archive_turns <= 0:
        parser.error("--max-pre-archive-turns must be positive.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_directory = (
        REPOSITORY_ROOT
        / "test"
        / "benchmark"
        / "results"
        / f"memory_archive_cycle_{timestamp}"
    )

    all_rows: list[dict] = []
    summaries: list[dict] = []

    started = time.perf_counter()

    for character_limit in args.limits:
        rows, summary = run_configuration(
            character_limit=character_limit,
            keep_recent_turns=args.keep_recent,
            temperature=args.temperature,
            num_predict=args.num_predict,
            max_pre_archive_turns=(args.max_pre_archive_turns),
        )

        all_rows.extend(rows)
        summaries.append(summary)

    summaries.sort(
        key=lambda item: (
            -(item["structured_checks_passed"] + item["post_archive_checks_passed"]),
            item["selection_score"],
            item["post_archive_first_token_p95"],
        )
    )

    write_csv(
        output_directory / "turn_results.csv",
        all_rows,
    )
    write_csv(
        output_directory / "summary.csv",
        summaries,
    )

    elapsed = time.perf_counter() - started

    print()
    print("=" * 78, flush=True)
    print("FINAL RANKING", flush=True)
    print("=" * 78, flush=True)

    for rank, summary in enumerate(
        summaries,
        start=1,
    ):
        print(
            f"{rank}. "
            f"limit={summary['character_limit']} "
            f"archive_turn={summary['archive_turn']} "
            f"prime={summary['prime_seconds']:.3f}s "
            f"post_first="
            f"{summary['post_archive_first_token_first']:.3f}s "
            f"post_p95="
            f"{summary['post_archive_first_token_p95']:.3f}s "
            f"score={summary['selection_score']:.3f} "
            f"structured="
            f"{summary['structured_checks_passed']}/"
            f"{summary['structured_checks_total']} "
            f"recall="
            f"{summary['post_archive_checks_passed']}/"
            f"{summary['post_archive_checks_total']}",
            flush=True,
        )

    print(
        f"Elapsed: {elapsed:.1f}s",
        flush=True,
    )
    print(
        f"Results: {output_directory}",
        flush=True,
    )


if __name__ == "__main__":
    main()
