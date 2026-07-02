#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from typing import Any


def text_sha256(value: str) -> str:
    return hashlib.sha256(
        str(value).encode("utf-8"),
    ).hexdigest()


def json_sha256(value: Any) -> str:
    canonical_json = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return text_sha256(canonical_json)


def log_prompt_identity(
    label: str,
    *,
    prefix_messages: list[dict[str, str]],
    full_messages: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    system_prompt = ""

    if prefix_messages:
        system_prompt = str(
            prefix_messages[0].get(
                "content",
                "",
            )
        )

    result = {
        "system_sha256": text_sha256(system_prompt),
        "prefix_sha256": json_sha256(prefix_messages),
    }

    if full_messages is not None:
        result["full_sha256"] = json_sha256(full_messages)

    fields = " ".join(
        f"{name}={value}"
        for name, value in result.items()
    )

    print(
        f"[PROMPT ID] "
        f"kind={label} "
        f"prefix_messages={len(prefix_messages)} "
        f"{fields}",
        flush=True,
    )

    return result
