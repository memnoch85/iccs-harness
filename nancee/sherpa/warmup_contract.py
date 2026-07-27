#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from prompt_contract import (
    build_prompt_messages_from_prefix,
    build_prompt_prefix,
)
from prompt_identity import (
    json_sha256,
    text_sha256,
)

# Version 2 replaces the conversational startup sentence with the same
# one-token prime contract used by the live TPC path.
WARMUP_FORMAT_VERSION = 2

CONTEXT_PRIME_USER_TEXT = "Internal context preparation. Reply with READY only."

WARMUP_STATE_FILE = Path(
    os.environ.get(
        "NANCEE_WARMUP_STATE_FILE",
        str(Path.home() / ".cache" / "nancee" / "ollama-warmup-state.json"),
    )
).expanduser()


def build_startup_warmup_prefix(
    system_prompt: str,
) -> list[dict[str, str]]:
    """Build the same empty-history base prefix used by ollama_runtime."""
    return build_prompt_prefix(
        system_prompt=system_prompt,
        history=[],
        memory_context="",
    )


def build_startup_warmup_messages(
    system_prompt: str,
) -> list[dict[str, str]]:
    prefix_messages = build_startup_warmup_prefix(
        system_prompt,
    )

    return build_prompt_messages_from_prefix(
        prefix_messages=prefix_messages,
        user_text=CONTEXT_PRIME_USER_TEXT,
        retrieved_context="",
        response_instruction="",
    )


def build_warmup_fingerprint(
    model: str,
    system_prompt: str,
) -> dict[str, object]:
    clean_prompt = str(system_prompt).strip()
    prefix_messages = build_startup_warmup_prefix(
        clean_prompt,
    )
    messages = build_prompt_messages_from_prefix(
        prefix_messages=prefix_messages,
        user_text=CONTEXT_PRIME_USER_TEXT,
        retrieved_context="",
        response_instruction="",
    )

    return {
        "model": str(model).strip(),
        "system_sha256": text_sha256(clean_prompt),
        "warmup_prefix_sha256": json_sha256(prefix_messages),
        "warmup_full_sha256": json_sha256(messages),
        "warmup_format_version": WARMUP_FORMAT_VERSION,
    }
