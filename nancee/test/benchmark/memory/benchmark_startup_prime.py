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
from ollama_runtime import (  # noqa: E402
    build_ollama_messages,
    prime_ollama_context,
)

LIVE_PROMPT = (
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
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Warmup failed with exit code {result.returncode}.")


def run_nonstreaming_prime(messages: list[dict[str, str]]) -> dict:
    payload = {
        "model": LLM_MODEL,
        "stream": False,
        "keep_alive": -1,
        "messages": messages,
        "options": {
            "temperature": 0.0,
            "num_thread": LLM_NUM_THREADS,
            "num_predict": 1,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()

    with urllib.request.urlopen(
        request,
        timeout=OLLAMA_RESPONSE_TIMEOUT,
    ) as response:
        data = json.load(response)

    return {
        "elapsed": time.perf_counter() - started,
        "prompt_eval": duration_seconds(
            data,
            "prompt_eval_duration",
        ),
        "prompt_tokens": data.get(
            "prompt_eval_count",
            0,
        ),
    }


def empty_user_prime() -> dict:
    messages = build_ollama_messages(
        user_text="",
        history=[],
        memory_context="",
        retrieved_context="",
    )

    return run_nonstreaming_prime(messages)


def run_live_request() -> dict:
    messages = build_ollama_messages(
        user_text=LIVE_PROMPT,
        history=[],
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
            "num_predict": 16,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    first_token = None
    final_data = None

    with urllib.request.urlopen(
        request,
        timeout=OLLAMA_RESPONSE_TIMEOUT,
    ) as response:
        for raw_line in response:
            data = json.loads(
                raw_line.decode(
                    "utf-8",
                    errors="replace",
                )
            )

            token = data.get(
                "message",
                {},
            ).get(
                "content",
                "",
            )

            if token and first_token is None:
                first_token = time.perf_counter() - started

            if data.get("done"):
                final_data = data
                break

    if first_token is None or final_data is None:
        raise RuntimeError("Live benchmark request did not complete.")

    return {
        "first_token": first_token,
        "prompt_eval": duration_seconds(
            final_data,
            "prompt_eval_duration",
        ),
        "prompt_tokens": final_data.get(
            "prompt_eval_count",
            0,
        ),
    }


def apply_strategy(strategy: str) -> dict | None:
    if strategy == "warmup_only":
        return None

    if strategy == "warmup_plus_context_prime":
        return prime_ollama_context(
            history=[],
            memory_context="",
        )

    if strategy == "warmup_plus_empty_user_prime":
        return empty_user_prime()

    raise ValueError(f"Unknown strategy: {strategy}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare startup priming strategies against the first real NANCEE request."
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
        "warmup_plus_context_prime",
        "warmup_plus_empty_user_prime",
    ]

    results: dict[str, list[dict]] = {strategy: [] for strategy in strategies}

    for repetition in range(
        1,
        args.repetitions + 1,
    ):
        for strategy in strategies:
            print()
            print("=" * 72)
            print(f"repetition={repetition} strategy={strategy}")
            print("=" * 72)

            stop_and_warm()

            prime_result = apply_strategy(strategy)

            if prime_result is not None:
                print(f"extra_prime={prime_result}")

            live_result = run_live_request()
            results[strategy].append(live_result)

            print(
                "live "
                f"first_token="
                f"{live_result['first_token']:.3f}s "
                f"prompt_eval="
                f"{live_result['prompt_eval']:.3f}s "
                f"prompt_tokens="
                f"{live_result['prompt_tokens']}"
            )

    print()
    print("=" * 72)
    print("FINAL STARTUP COMPARISON")
    print("=" * 72)

    for strategy in strategies:
        first_tokens = [result["first_token"] for result in results[strategy]]

        prompt_evals = [result["prompt_eval"] for result in results[strategy]]

        print(
            f"{strategy}: "
            f"first_median="
            f"{statistics.median(first_tokens):.3f}s "
            f"first_min={min(first_tokens):.3f}s "
            f"first_max={max(first_tokens):.3f}s "
            f"prompt_eval_median="
            f"{statistics.median(prompt_evals):.3f}s"
        )


if __name__ == "__main__":
    main()
