from __future__ import annotations

import re


_USER_ACTIONS = (
    "bought|purchased|got|ordered|picked|found|drove|went|visited|"
    "ate|drank|saw|owned|used|installed|made|told|said"
)


def looks_like_perspective_correction(user_text: str) -> bool:
    text = re.sub(r"\s+", " ", str(user_text).strip().lower())

    patterns = (
        r"\b(?:you|nancee|nancy)\b.+\bor\b.+\bi\b",
        r"\bi\b.+\bor\b.+\b(?:you|nancee|nancy)\b",
        r"\bwas it (?:you|me|i)\b.+\bor\b.+\b(?:you|me|i)\b",
        r"\bdid you .+ or did i\b",
        r"\bdid i .+ or did you\b",
    )

    return any(re.search(pattern, text) for pattern in patterns)


def repair_recall_perspective(response_text: str) -> tuple[str, bool]:
    """Repair narrow self-attribution errors in a memory-grounded answer."""
    text = str(response_text).strip()
    original = text

    text = re.sub(
        rf"^(\s*(?:actually[, ]+|today[, ]+|yesterday[, ]+)?)I\s+({_USER_ACTIONS})\b",
        lambda match: (
            f"{match.group(1)}"
            f"{'You' if not match.group(1).strip() else 'you'} "
            f"{match.group(2)}"
        ),
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        rf"\bit was me who\s+({_USER_ACTIONS})\b",
        lambda match: f"it was you who {match.group(1)}",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        rf"\bI was the one who\s+({_USER_ACTIONS})\b",
        lambda match: f"you were the one who {match.group(1)}",
        text,
        flags=re.IGNORECASE,
    )

    return text, text != original
