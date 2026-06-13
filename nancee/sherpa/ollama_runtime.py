import json
import subprocess
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
    load_system_prompt,
)


def is_ollama_model_loaded(model_name):
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


def ensure_ollama_model_loaded(model_name):
    if is_ollama_model_loaded(model_name):
        print(
            f"[LLM READY] {model_name!r} is already loaded.",
            flush=True,
        )
        return

    print(
        f"[LLM WARMUP] {model_name!r} is not loaded. "
        "Starting warmup...",
        flush=True,
    )

    try:
        result = subprocess.run(
            [
                OLLAMA_WARMUP_COMMAND,
                model_name,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=OLLAMA_WARMUP_TIMEOUT,
        )

    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Warmup timed out for model {model_name!r}"
        ) from error

    except OSError as error:
        raise RuntimeError(
            f"Could not execute "
            f"{OLLAMA_WARMUP_COMMAND!r}: {error}"
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
            f"Warmup failed for {model_name!r}; "
            f"exit code={result.returncode}"
        )

    if not is_ollama_model_loaded(model_name):
        raise RuntimeError(
            f"Warmup completed, but {model_name!r} "
            "is not listed as loaded by Ollama."
        )

    print(
        f"[LLM READY] {model_name!r} responded and is loaded.",
        flush=True,
    )


def stream_ollama_response(user_text):
    system_prompt = load_system_prompt()

    payload = {
        "model": LLM_MODEL,
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_text,
            },
        ],
        "options": {
            "temperature": LLM_TEMPERATURE,
            "num_thread": LLM_NUM_THREADS,
            "num_predict": LLM_NUM_PREDICT,
        },
    }

    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=OLLAMA_RESPONSE_TIMEOUT,
    ) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()

            if not line:
                continue

            data = json.loads(line)

            if data.get("done"):
                break

            token = (
                data.get("message", {})
                .get("content", "")
            )

            if token:
                yield token
