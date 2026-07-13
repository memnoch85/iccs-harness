from __future__ import annotations

import re


_TEMPORAL_PREFIX = (
    r"(?:actually[, ]+|today[, ]+|yesterday[, ]+)?"
)


_NANCEE_FIRST_PERSON_PREFIX = re.compile(
    rf"""
    ^\s*
    {_TEMPORAL_PREFIX}
    (?:
        I\s+
        (?:
            remember
            |recall
            |think
            |believe
            |know
            |understand
        )\b

        |

        I\s+
        (?:
            do\ not
            |don't
            |cannot
            |can't
        )
        \s+
        (?:
            remember
            |recall
            |verify
        )\b

        |

        I(?:'m|\ am)\s+
        (?:
            not\ sure
            |unable
        )\b
    )
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


def looks_like_perspective_correction(
    user_text: str,
) -> bool:
    text = re.sub(
        r"\s+",
        " ",
        str(user_text).strip().lower(),
    )

    patterns = (
        r"\b(?:you|nancee|nancy)\b.+\bor\b.+\bi\b",
        r"\bi\b.+\bor\b.+\b(?:you|nancee|nancy)\b",
        r"\bwas it (?:you|me|i)\b.+\bor\b.+\b(?:you|me|i)\b",
        r"\bdid you .+ or did i\b",
        r"\bdid i .+ or did you\b",
    )

    return any(
        re.search(pattern, text)
        for pattern in patterns
    )


def _subject_word(
    prefix: str,
    capitalized: str,
    lowercase: str,
) -> str:
    if prefix.strip():
        return lowercase

    return capitalized


def repair_recall_perspective(
    response_text: str,
) -> tuple[str, bool]:
    """
    Convert a retrieved human-user fact from first person
    into second person before TTS and recent history.

    Preserve legitimate Nancee statements such as:
      I remember...
      I don't recall...
      I'm not sure...
    """
    text = (
        str(response_text)
        .strip()
        .replace("’", "'")
    )

    original = text

    if not text:
        return text, False

    if _NANCEE_FIRST_PERSON_PREFIX.match(text):
        return text, False

    # "Actually, it was me who bought..."
    text = re.sub(
        r"\bit was me who\b",
        "it was you who",
        text,
        flags=re.IGNORECASE,
    )

    # Handle first-person forms whose verb changes
    # when converted to second person.
    text = re.sub(
        rf"^(\s*{_TEMPORAL_PREFIX})I\s+am\b",
        lambda match: (
            f"{match.group(1)}"
            f"{_subject_word(match.group(1), 'You', 'you')} "
            "are"
        ),
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        rf"^(\s*{_TEMPORAL_PREFIX})I'm\b",
        lambda match: (
            match.group(1)
            + _subject_word(
                match.group(1),
                "You're",
                "you're",
            )
        ),
        text,
        flags=re.IGNORECASE,
    )


    text = re.sub(
        rf"^(\s*{_TEMPORAL_PREFIX})I\s+was\b",
        lambda match: (
            f"{match.group(1)}"
            f"{_subject_word(match.group(1), 'You', 'you')} "
            "were"
        ),
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        rf"^(\s*{_TEMPORAL_PREFIX})I've\b",
        lambda match: (
            match.group(1)
            + _subject_word(
                match.group(1),
                "You've",
                "you've",
            )
        ),
        text,
        flags=re.IGNORECASE,
    )


    # Other verbs keep the same form:
    # I wired -> You wired
    # I bought -> You bought
    # I have -> You have
    text = re.sub(
        rf"^(\s*{_TEMPORAL_PREFIX})I\b",
        lambda match: (
            f"{match.group(1)}"
            f"{_subject_word(match.group(1), 'You', 'you')}"
        ),
        text,
        flags=re.IGNORECASE,
    )

    # My car -> Your car
    text = re.sub(
        rf"^(\s*{_TEMPORAL_PREFIX})My\b",
        lambda match: (
            f"{match.group(1)}"
            f"{_subject_word(match.group(1), 'Your', 'your')}"
        ),
        text,
        flags=re.IGNORECASE,
    )

    # Mine -> Yours
    text = re.sub(
        rf"^(\s*{_TEMPORAL_PREFIX})Mine\b",
        lambda match: (
            f"{match.group(1)}"
            f"{_subject_word(match.group(1), 'Yours', 'yours')}"
        ),
        text,
        flags=re.IGNORECASE,
    )

    return text, text != original
