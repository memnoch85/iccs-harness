from __future__ import annotations

import re
from collections.abc import Mapping


_SENTENCE_END_PATTERN = re.compile(
    r"""[.!?](?:["')\]]+)?""",
)

_TERMINAL_END_PATTERN = re.compile(
    r"""[.!?](?:["')\]]+)?\s*$""",
)

_PROMPT_ROLE_LEAK_PATTERN = re.compile(
    r"(?im)(?:^|\n)[ \t]*"
    r"(?:"
    r"(?:USER MESSAGE|ASSISTANT|SYSTEM|TURN RESPONSE CONSTRAINT)"
    r"[ \t]*:"
    r"|REMEMBER[ \t]*:[ \t\r\n]*"
    r"(?:"
    r"KEEP RESPONSES"
    r"|ANSWER ONLY WHAT THE USER ASKED"
    r"|DO NOT ADD STORIES"
    r"|NEVER OUTPUT PARENTHETICAL"
    r"|MATCH THE RESPONSE SIZE"
    r"|SPEAK ONLY TO THE CURRENT USER"
    r"|ASK A FOLLOW-UP ONLY"
    r"|BEGIN WITH ONE NATURAL"
    r")"
    r"|KEEP RESPONSES[ \t]+CONCISE\b"
    r"|ANSWER ONLY WHAT THE USER ASKED\b"
    r"|DO NOT ADD STORIES\b"
    r"|NEVER OUTPUT PARENTHETICAL\b"
    r"|MATCH THE RESPONSE SIZE\b"
    r"|SPEAK ONLY TO THE CURRENT USER\b"
    r")",
)


def done_reason(completion_state: Mapping | None) -> str:
    if not completion_state:
        return ""

    return str(
        completion_state.get(
            "done_reason",
            "",
        )
    ).strip().lower()


def final_fragment_is_safe(
    fragment: str,
    completion_state: Mapping | None,
) -> bool:
    cleaned = str(fragment).strip()

    if not cleaned:
        return False

    if done_reason(completion_state) != "length":
        return True

    return bool(_TERMINAL_END_PATTERN.search(cleaned))


def trim_incomplete_length_tail(
    text: str,
    completion_state: Mapping | None,
) -> tuple[str, bool]:
    """
    Keep normal completions unchanged.

    When Ollama reports done_reason=length, retain only text through the
    final complete sentence so a cut-off tail does not enter recent history.
    """
    cleaned = re.sub(
        r"\s+",
        " ",
        str(text).strip(),
    )

    if not cleaned:
        return "", False

    if done_reason(completion_state) != "length":
        return cleaned, False

    endings = list(
        _SENTENCE_END_PATTERN.finditer(cleaned)
    )

    if not endings:
        return "", True

    boundary = endings[-1].end()
    return cleaned[:boundary].strip(), boundary < len(cleaned)


def trim_prompt_role_leak(
    text: str,
) -> tuple[str, bool]:
    """Remove a generated prompt-role continuation before it reaches TTS."""
    raw = str(text)
    match = _PROMPT_ROLE_LEAK_PATTERN.search(raw)

    if match is None:
        return raw, False

    return raw[: match.start()].rstrip(), True


def prepare_clarification_response(
    text: str,
    completion_state: Mapping | None,
) -> tuple[str, str]:
    """Return one complete clarification sentence or a deterministic fallback."""
    cleaned, role_leak_trimmed = trim_prompt_role_leak(text)
    cleaned, length_tail_trimmed = trim_incomplete_length_tail(
        cleaned,
        completion_state,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return "Could you repeat that?", "fallback"

    first_ending = _SENTENCE_END_PATTERN.search(cleaned)

    if first_ending is not None:
        cleaned = cleaned[: first_ending.end()].strip()

    if role_leak_trimmed:
        return cleaned, "prompt_role_leak_trimmed"

    if length_tail_trimmed:
        return cleaned, "length_tail_trimmed"

    return cleaned, "accepted"
