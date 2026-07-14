from __future__ import annotations

import re
from collections.abc import Mapping


_SENTENCE_END_PATTERN = re.compile(
    r"""[.!?](?:["')\]]+)?""",
)

_TERMINAL_END_PATTERN = re.compile(
    r"""[.!?](?:["')\]]+)?\s*$""",
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
