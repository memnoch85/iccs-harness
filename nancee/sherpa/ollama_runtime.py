from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request

from config import (
    LLM_MODEL,
    LLM_NUM_PREDICT,
    LLM_NUM_THREADS,
    LLM_TEMPERATURE,
    OLLAMA_PS_URL,
    OLLAMA_RESPONSE_TIMEOUT,
    OLLAMA_STATUS_TIMEOUT,
    OLLAMA_URL,
    OLLAMA_WARMUP_COMMAND,
    OLLAMA_WARMUP_TIMEOUT,
    SHERPA_DIRECTORY,
    load_system_prompt,
)
from iccs import ICCS
from prompt_contract import (
    build_prompt_messages_from_prefix,
    build_prompt_prefix,
)
from prompt_identity import json_sha256, log_prompt_identity
from warmup_contract import (
    CONTEXT_PRIME_EXPECTED_REPLY,
    CONTEXT_PRIME_NUM_PREDICT,
    CONTEXT_PRIME_TEMPERATURE,
    CONTEXT_PRIME_USER_TEXT,
    WARMUP_STATE_FILE,
    build_warmup_fingerprint,
)

# Keep Ollama requests serialized for predictable local-model behavior.
_OLLAMA_REQUEST_LOCK = threading.Lock()


def duration_seconds(
    data: dict,
    field: str,
) -> float:
    return data.get(field, 0) / 1_000_000_000


def build_ollama_prefix_messages(
    *,
    history=None,
    memory_context="",
):
    return build_prompt_prefix(
        system_prompt=load_system_prompt(),
        history=history,
        memory_context=memory_context,
    )


def ollama_prefix_sha256(
    *,
    history=None,
    memory_context="",
):
    return json_sha256(
        build_ollama_prefix_messages(
            history=history,
            memory_context=memory_context,
        )
    )


def build_ollama_messages_from_prefix(
    *,
    prefix_messages,
    user_text,
    retrieved_context="",
    response_instruction="",
):
    return build_prompt_messages_from_prefix(
        prefix_messages=prefix_messages,
        user_text=user_text,
        retrieved_context=retrieved_context,
        response_instruction=response_instruction,
    )


def build_ollama_messages(
    *,
    user_text,
    history=None,
    memory_context="",
    retrieved_context="",
    response_instruction="",
):
    prefix_messages = build_ollama_prefix_messages(
        history=history,
        memory_context=memory_context,
    )

    return build_ollama_messages_from_prefix(
        prefix_messages=prefix_messages,
        user_text=user_text,
        retrieved_context=retrieved_context,
        response_instruction=response_instruction,
    )

def is_ollama_model_loaded(
    model_name,
):
    request = urllib.request.Request(
        OLLAMA_PS_URL,
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_STATUS_TIMEOUT,
        ) as response:
            data = json.load(response)

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"[LLM STATUS] Could not query Ollama: {error}",
            flush=True,
        )
        return False

    for model in data.get("models", []):
        loaded_name = model.get("name") or model.get("model")

        if loaded_name == model_name:
            return True

    return False


def load_warmup_state():
    try:
        state = json.loads(
            WARMUP_STATE_FILE.read_text(
                encoding="utf-8",
            )
        )

    except FileNotFoundError:
        print(
            f"[WARMUP STATE] missing={WARMUP_STATE_FILE}",
            flush=True,
        )
        return None

    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"[WARMUP STATE] invalid={WARMUP_STATE_FILE} error={error!r}",
            flush=True,
        )
        return None

    if not isinstance(state, dict):
        print(
            "[WARMUP STATE] State file does not contain an object.",
            flush=True,
        )
        return None

    return state


def is_current_warmup_state(
    model_name,
):
    expected = build_warmup_fingerprint(
        model_name,
        load_system_prompt(),
    )

    actual = load_warmup_state()

    if actual is None:
        return False

    compared_fields = (
        "model",
        "system_sha256",
        "warmup_prefix_sha256",
        "warmup_full_sha256",
        "warmup_format_version",
    )

    mismatches = [
        field for field in compared_fields if actual.get(field) != expected.get(field)
    ]

    if mismatches:
        print(
            "[WARMUP STATE] "
            "match=false "
            f"mismatches={mismatches} "
            f"expected_model={expected['model']} "
            f"actual_model={actual.get('model')} "
            f"expected_system={expected['system_sha256']} "
            f"actual_system={actual.get('system_sha256')}",
            flush=True,
        )
        return False

    print(
        "[WARMUP STATE] "
        "match=true "
        f"model={expected['model']} "
        f"system_sha256={expected['system_sha256']} "
        f"prefix_sha256={expected['warmup_prefix_sha256']} "
        f"full_sha256={expected['warmup_full_sha256']}",
        flush=True,
    )

    return True


def ensure_ollama_model_loaded(
    model_name,
):
    startup_prefix = build_ollama_prefix_messages(
        history=[],
        memory_context="",
    )

    log_prompt_identity(
        "startup",
        prefix_messages=startup_prefix,
        full_messages=startup_prefix,
    )

    model_loaded = is_ollama_model_loaded(model_name)

    warmup_current = is_current_warmup_state(model_name)

    if model_loaded and warmup_current:
        print(
            f"[LLM READY] {model_name!r} is loaded and the current prompt is warmed.",
            flush=True,
        )
        return

    reasons = []

    if not model_loaded:
        reasons.append("model is not loaded")

    if not warmup_current:
        reasons.append("warmup fingerprint is missing or stale")

    print(
        f"[LLM WARMUP] Starting warmup for {model_name!r}: {'; '.join(reasons)}",
        flush=True,
    )

    try:
        warmup_environment = os.environ.copy()

        existing_python_path = warmup_environment.get(
            "PYTHONPATH",
            "",
        ).strip()

        warmup_python_paths = [
            str(SHERPA_DIRECTORY),
        ]

        if existing_python_path:
            warmup_python_paths.append(
                existing_python_path,
            )

        warmup_environment["PYTHONPATH"] = os.pathsep.join(
            warmup_python_paths
        )

        result = subprocess.run(
            [
                OLLAMA_WARMUP_COMMAND,
                model_name,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=OLLAMA_WARMUP_TIMEOUT,
            cwd=str(SHERPA_DIRECTORY),
            env=warmup_environment,
        )

    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Warmup timed out for model {model_name!r} after {OLLAMA_WARMUP_TIMEOUT}s"
        ) from error

    except OSError as error:
        raise RuntimeError(
            f"Could not execute {OLLAMA_WARMUP_COMMAND!r}: {error}"
        ) from error

    if result.stdout:
        print(
            result.stdout.strip(),
            flush=True,
        )

    if result.stderr:
        print(
            result.stderr.strip(),
            flush=True,
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"Warmup failed for model {model_name!r}; exit code={result.returncode}"
        )

    if not is_ollama_model_loaded(model_name):
        raise RuntimeError(
            f"Warmup completed, but {model_name!r} is not listed as loaded by Ollama."
        )

    if not is_current_warmup_state(model_name):
        raise RuntimeError(
            "Warmup completed, but its saved "
            "fingerprint does not match the "
            "current model and system prompt."
        )

    print(
        "[LLM READY] "
        f"{model_name!r} responded, is loaded, "
        "and has the current prompt fingerprint.",
        flush=True,
    )


def prime_ollama_context(
    *,
    prefix_messages=None,
    history=None,
    memory_context="",
):
    if prefix_messages is None:
        prefix_messages = build_ollama_prefix_messages(
            history=history,
            memory_context=memory_context,
        )

    messages = build_ollama_messages_from_prefix(
        prefix_messages=prefix_messages,
        user_text=CONTEXT_PRIME_USER_TEXT,
        retrieved_context="",
        response_instruction="",
    )

    identity = log_prompt_identity(
        "prime",
        prefix_messages=list(prefix_messages),
        full_messages=messages,
    )

    payload = {
        "model": LLM_MODEL,
        "stream": False,
        "keep_alive": -1,
        "messages": messages,
        "options": {
            "temperature": CONTEXT_PRIME_TEMPERATURE,
            "num_thread": LLM_NUM_THREADS,
            "num_predict": CONTEXT_PRIME_NUM_PREDICT,
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

    try:
        with (
            _OLLAMA_REQUEST_LOCK,
            urllib.request.urlopen(
                request,
                timeout=OLLAMA_RESPONSE_TIMEOUT,
            ) as response,
        ):
            data = json.load(response)

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
    ) as error:
        raise RuntimeError(f"Ollama context prime failed: {error}") from error

    if data.get("error"):
        raise RuntimeError(f"Ollama context prime returned an error: {data['error']}")

    prime_reply = str(
        data.get("message", {}).get("content", "")
    ).strip()

    if prime_reply != CONTEXT_PRIME_EXPECTED_REPLY:
        raise RuntimeError(
            "Ollama context prime returned the wrong disposable token: "
            f"expected={CONTEXT_PRIME_EXPECTED_REPLY!r} "
            f"actual={prime_reply!r}"
        )

    elapsed = time.perf_counter() - started

    result = {
        "elapsed_seconds": elapsed,
        "load_seconds": duration_seconds(
            data,
            "load_duration",
        ),
        "prompt_tokens": data.get(
            "prompt_eval_count",
            0,
        ),
        "prompt_eval_seconds": duration_seconds(
            data,
            "prompt_eval_duration",
        ),
        "generation_seconds": duration_seconds(
            data,
            "eval_duration",
        ),
        "response_tokens": data.get(
            "eval_count",
            0,
        ),
        "prime_reply": prime_reply,
        **identity,
    }

    print(
        "[LLM CONTEXT PRIME] "
        f"elapsed={result['elapsed_seconds']:.3f}s "
        f"load={result['load_seconds']:.3f}s "
        f"prompt_eval={result['prompt_eval_seconds']:.3f}s "
        f"generation={result['generation_seconds']:.3f}s "
        f"prompt_tokens={result['prompt_tokens']} "
        f"response_tokens={result['response_tokens']} "
        f"prime_reply={result['prime_reply']} "
        f"system_sha256={identity['system_sha256']} "
        f"prefix_sha256={identity['prefix_sha256']}",
        flush=True,
    )

    return result

def stream_ollama_response(
    user_text,
    history=None,
    memory_context="",
    prefix_messages=None,
    prefix_source=None,
    retrieved_context="",
    response_instruction="",
    temperature=None,
    num_predict=None,
    completion_state=None,
):
    request_started = time.perf_counter()
    first_token_seconds = None

    if completion_state is not None:
        completion_state.clear()
        completion_state.update(
            done_reason="",
            response_tokens=0,
            first_token_seconds=None,
            total_seconds=None,
            load_seconds=0.0,
            prompt_eval_seconds=0.0,
            generation_seconds=0.0,
            prompt_tokens=0,
        )

    if prefix_messages is None:
        prefix_messages = build_ollama_prefix_messages(
            history=history,
            memory_context=memory_context,
        )
        prefix_source = "rebuilt"
    else:
        prefix_messages = list(prefix_messages)
        prefix_source = str(prefix_source or "provided_snapshot")

    messages = build_ollama_messages_from_prefix(
        prefix_messages=prefix_messages,
        user_text=user_text,
        retrieved_context=retrieved_context,
        response_instruction=response_instruction,
    )

    identity = log_prompt_identity(
        "request",
        prefix_messages=prefix_messages,
        full_messages=messages,
    )

    print(
        "[PROMPT SHAPE] "
        f"messages={len(messages)} "
        f"prefix_messages={len(prefix_messages)} "
        f"history_messages={len(history or [])} "
        f"prefix_source={prefix_source} "
        f"retrieved_context_chars="
        f"{len(str(retrieved_context).strip())} "
        f"memory_context_chars="
        f"{len(str(memory_context).strip())}",
        flush=True,
    )

    if (
        os.getenv(
            "NANCEE_MEMORY_DEBUG",
            "false",
        ).lower()
        == "true"
    ):
        print(
            "[MEMORY DEBUG] Ollama messages:",
            flush=True,
        )
        print(
            json.dumps(
                messages,
                indent=2,
                default=str,
            ),
            flush=True,
        )

    effective_temperature = (
        LLM_TEMPERATURE
        if temperature is None
        else float(temperature)
    )

    effective_num_predict = (
        LLM_NUM_PREDICT
        if num_predict is None
        else int(num_predict)
    )

    if effective_temperature < 0:
        raise ValueError(
            "temperature cannot be negative."
        )

    if effective_num_predict <= 0:
        raise ValueError(
            "num_predict must be positive."
        )

    print(
        "[LLM REQUEST OPTIONS] "
        f"temperature={effective_temperature:.2f} "
        f"num_predict={effective_num_predict}",
        flush=True,
    )

    payload = {
        "model": LLM_MODEL,
        "stream": True,
        "keep_alive": -1,
        "messages": messages,
        "options": {
            "temperature": effective_temperature,
            "num_thread": LLM_NUM_THREADS,
            "num_predict": effective_num_predict,
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

    try:
        with (
            _OLLAMA_REQUEST_LOCK,
            urllib.request.urlopen(
                request,
                timeout=OLLAMA_RESPONSE_TIMEOUT,
            ) as response,
        ):
            for raw_line in response:
                line = raw_line.decode(
                    "utf-8",
                    errors="replace",
                ).strip()

                if not line:
                    continue

                try:
                    data = json.loads(line)

                except json.JSONDecodeError as error:
                    raise RuntimeError(
                        "Ollama returned invalid JSON: "
                        f"{error}"
                    ) from error

                if data.get("error"):
                    raise RuntimeError(
                        "Ollama returned an error: "
                        f"{data['error']}"
                    )

                token = data.get(
                    "message",
                    {},
                ).get(
                    "content",
                    "",
                )

                if token:
                    if first_token_seconds is None:
                        first_token_seconds = (
                            time.perf_counter()
                            - request_started
                        )

                        if completion_state is not None:
                            completion_state[
                                "first_token_seconds"
                            ] = first_token_seconds

                    yield token

                if data.get("done"):
                    request_total_seconds = (
                        time.perf_counter()
                        - request_started
                    )

                    if completion_state is not None:
                        completion_state.update(
                            done_reason=data.get(
                                "done_reason",
                                "unknown",
                            ),
                            response_tokens=data.get(
                                "eval_count",
                                0,
                            ),
                            total_seconds=(
                                request_total_seconds
                            ),
                            load_seconds=duration_seconds(
                                data,
                                "load_duration",
                            ),
                            prompt_eval_seconds=(
                                duration_seconds(
                                    data,
                                    "prompt_eval_duration",
                                )
                            ),
                            generation_seconds=(
                                duration_seconds(
                                    data,
                                    "eval_duration",
                                )
                            ),
                            prompt_tokens=data.get(
                                "prompt_eval_count",
                                0,
                            ),
                        )

                    print(
                        "\n[OLLAMA DONE] "
                        f"reason="
                        f"{data.get('done_reason', 'unknown')} "
                        f"load="
                        f"{duration_seconds(data, 'load_duration'):.3f}s "
                        f"prompt_eval="
                        f"{duration_seconds(data, 'prompt_eval_duration'):.3f}s "
                        f"generation="
                        f"{duration_seconds(data, 'eval_duration'):.3f}s "
                        f"prompt_tokens="
                        f"{data.get('prompt_eval_count', 0)} "
                        f"response_tokens="
                        f"{data.get('eval_count', 0)} "
                        f"system_sha256="
                        f"{identity['system_sha256']} "
                        f"prefix_sha256="
                        f"{identity['prefix_sha256']} "
                        f"full_sha256="
                        f"{identity.get('full_sha256', '')}",
                        flush=True,
                    )
                    break

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
    ) as error:
        raise RuntimeError(
            f"Ollama request failed: {error}"
        ) from error


class OllamaIccsBackend:
    """Bind the reusable ICCS lifecycle to NANCEE's proven Ollama path."""

    def build_prefix(self, *, history, memory_context):
        return build_ollama_prefix_messages(
            history=history,
            memory_context=memory_context,
        )

    def fingerprint(self, prefix_messages):
        return json_sha256(prefix_messages)

    def prime(self, *, prefix_messages):
        return prime_ollama_context(
            prefix_messages=prefix_messages,
        )

    def stream(
        self,
        *,
        prefix_messages,
        prefix_source,
        history,
        memory_context,
        **request_kwargs,
    ):
        yield from stream_ollama_response(
            prefix_messages=prefix_messages,
            prefix_source=prefix_source,
            history=history,
            memory_context=memory_context,
            **request_kwargs,
        )


def create_ollama_iccs():
    """Create ICCS with NANCEE's unchanged prompt and Ollama functions."""
    return ICCS(backend=OllamaIccsBackend())
