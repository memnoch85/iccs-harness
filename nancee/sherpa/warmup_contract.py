#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from prompt_identity import (
    json_sha256,
    text_sha256,
)

WARMUP_FORMAT_VERSION = 1

STARTUP_WARMUP_USER_TEXT = (
    "This is the Nancee startup warmup request. "
    "Reply with one short sentence saying that "
    "Nancee is online and ready to ride."
)

CONTEXT_PRIME_USER_TEXT = "Internal context preparation. Reply with READY only."

WARMUP_STATE_FILE = Path(
    os.environ.get(
        "NANCEE_WARMUP_STATE_FILE",
        str(Path.home() / ".cache" / "nancee" / "ollama-warmup-state.json"),
    )
).expanduser()


def build_startup_warmup_messages(
    system_prompt: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": str(system_prompt).strip(),
        },
        {
            "role": "user",
            "content": STARTUP_WARMUP_USER_TEXT,
        },
    ]


def build_warmup_fingerprint(
    model: str,
    system_prompt: str,
) -> dict[str, object]:
    clean_prompt = str(system_prompt).strip()

    messages = build_startup_warmup_messages(clean_prompt)

    return {
        "model": str(model).strip(),
        "system_sha256": text_sha256(clean_prompt),
        "warmup_full_sha256": json_sha256(messages),
        "warmup_format_version": WARMUP_FORMAT_VERSION,
    }
