#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.request
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
from ollama_runtime import build_ollama_messages  # noqa: E402

SEED_USER_TEXT = (
    "This is a hidden startup seed turn. "
    "Reply with one short sentence saying Nancee is ready."
)

LIVE_USER_TEXT = (
    "My name is Anders. My favorite band is Finch. "
    "I drive a 2016 Jeep Patriot with code P0420. "
    "Acknowledge this briefly."
)


def duration_seconds(data: dict, field: str) -> float:
    return data.get(field, 0) / 1_000_000_000


def stop_and_warm() -> None:
    subprocess.run(
        ["ollama", "stop", LLM_MODEL],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(1.0)

    result = subprocess.run(
        [OLLAMA_WARMUP_COMMAND, LLM_MODEL],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr)

        if result.stderr:
            print(result.stderr, file=sys.stderr)

        raise RuntimeError(f"Warmup failed with exit code {result.returncode}.")


def stream_request(
    *,
    user_text: str,
    history: list[dict[str, str]],
    num_predict: int,
) -> dict:
    messages = build_ollama_messages(
        user_text=user_text,
        history=history,
        memory_context="",
        retrieved_context="",
    )

    payload = {
        "model": LLM_MODEL,
        "stream": True,
        "keep_alive": -1,
        "messages": messages,
        "options": {
            "temperature": 0.0,
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

    if first_token_seconds is None or final_data is None:
        raise RuntimeError("Benchmark request did not complete.")

    return {
        "response_text": "".join(response_parts).strip(),
        "first_token_seconds": (first_token_seconds),
        "prompt_eval_seconds": duration_seconds(
            final_data,
            "prompt_eval_duration",
        ),
        "prompt_tokens": final_data.get(
            "prompt_eval_count",
            0,
        ),
    }


def run_strategy(strategy: str) -> dict:
    stop_and_warm()

    seed_result = None
    live_history: list[dict[str, str]] = []

    if strategy in {
        "seed_discarded",
        "seed_carried",
    }:
        seed_result = stream_request(
            user_text=SEED_USER_TEXT,
            history=[],
            num_predict=20,
        )

        print(
            "seed "
            f"first={seed_result['first_token_seconds']:.3f}s "
            f"prompt_eval={seed_result['prompt_eval_seconds']:.3f}s "
            f"reply={seed_result['response_text']!r}",
            flush=True,
        )

        if strategy == "seed_carried":
            live_history = [
                {
                    "role": "user",
                    "content": SEED_USER_TEXT,
                },
                {
                    "role": "assistant",
                    "content": seed_result["response_text"],
                },
            ]

    live_result = stream_request(
        user_text=LIVE_USER_TEXT,
        history=live_history,
        num_predict=20,
    )

    print(
        "live "
        f"first={live_result['first_token_seconds']:.3f}s "
        f"prompt_eval={live_result['prompt_eval_seconds']:.3f}s "
        f"prompt_tokens={live_result['prompt_tokens']}",
        flush=True,
    )

    return live_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Test whether carrying a discarded startup seed turn "
            "into hidden model history removes first-live-turn latency."
        )
    )

    parser.add_argument(
        "--repetitions",
        type=int,
        default=2,
    )

    args = parser.parse_args()

    if args.repetitions <= 0:
        parser.error("--repetitions must be positive.")

    strategies = [
        "warmup_only",
        "seed_discarded",
        "seed_carried",
    ]

    results: dict[str, list[dict]] = {strategy: [] for strategy in strategies}

    for repetition in range(
        1,
        args.repetitions + 1,
    ):
        for strategy in strategies:
            print()
            print("=" * 72, flush=True)
            print(
                f"repetition={repetition} strategy={strategy}",
                flush=True,
            )
            print("=" * 72, flush=True)

            results[strategy].append(run_strategy(strategy))

    print()
    print("=" * 72, flush=True)
    print(
        "FINAL STARTUP SEED COMPARISON",
        flush=True,
    )
    print("=" * 72, flush=True)

    for strategy in strategies:
        first_tokens = [row["first_token_seconds"] for row in results[strategy]]
        prompt_evals = [row["prompt_eval_seconds"] for row in results[strategy]]

        print(
            f"{strategy}: "
            f"first_median="
            f"{statistics.median(first_tokens):.3f}s "
            f"first_min={min(first_tokens):.3f}s "
            f"first_max={max(first_tokens):.3f}s "
            f"prompt_eval_median="
            f"{statistics.median(prompt_evals):.3f}s",
            flush=True,
        )


if __name__ == "__main__":
    main()
