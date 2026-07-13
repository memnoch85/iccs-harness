from __future__ import annotations

import re


_LEADING_DISCOURSE = re.compile(
    r"^(?:(?:so|well|okay|ok|hey|hello|hi|also|and)\s+)*"
    r"(?:(?:nancy|nancee)[,\s]+)?",
    flags=re.IGNORECASE,
)

_QUESTION_PREFIXES = (
    "what ",
    "who ",
    "where ",
    "when ",
    "why ",
    "how ",
    "do ",
    "does ",
    "did ",
    "can ",
    "could ",
    "would ",
    "should ",
    "is ",
    "are ",
    "am ",
    "was ",
    "were ",
)

_COMMAND_PREFIXES = (
    "tell me ",
    "show me ",
    "explain ",
    "describe ",
    "give me ",
    "find ",
    "look up ",
    "search ",
    "remember ",
    "remind me ",
    "help me ",
    "please ",
)

_I_FACT_VERBS = (
    "am",
    "have",
    "own",
    "drive",
    "bought",
    "purchased",
    "got",
    "keep",
    "kept",
    "left",
    "put",
    "parked",
    "live",
    "work",
    "like",
    "love",
    "prefer",
    "use",
    "need",
    "want",
    "went",
    "ordered",
    "ate",
    "met",
    "saw",
    "called",
    "found",
    "lost",
)

_WE_FACT_VERBS = (
    "are",
    "have",
    "own",
    "drive",
    "bought",
    "purchased",
    "got",
    "keep",
    "left",
    "live",
    "work",
    "like",
    "love",
    "prefer",
    "use",
    "need",
    "want",
)

_POSSESSIVE_ASSIGNMENT_VERBS = (
    "is",
    "are",
    "was",
    "were",
    "has",
    "have",
    "contains",
    "includes",
)


def normalize_memory_candidate(text: str) -> str:
    normalized = str(text).strip()
    normalized = normalized.replace("’", "'")
    normalized = _LEADING_DISCOURSE.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def looks_like_personal_fact_fragment(text: str) -> bool:
    """Return True for short fact-shaped fragments such as 'My wife's name.'"""
    normalized = normalize_memory_candidate(text)
    lowered = normalized.lower().rstrip(".!,;:")

    if not lowered or "?" in normalized:
        return False

    words = re.findall(r"[a-z0-9']+", lowered)

    if not 2 <= len(words) <= 8:
        return False

    if words[0] not in {"my", "our"}:
        return False

    if any(
        re.search(rf"\b{re.escape(verb)}\b", lowered)
        for verb in _POSSESSIVE_ASSIGNMENT_VERBS
    ):
        return False

    return True


def looks_like_question_or_command(text: str) -> bool:
    normalized = normalize_memory_candidate(text)
    lowered = normalized.lower()

    if not lowered:
        return False

    if "?" in normalized:
        return True

    if lowered.startswith(_QUESTION_PREFIXES):
        return True

    if lowered.startswith(_COMMAND_PREFIXES):
        return True

    return looks_like_personal_fact_fragment(normalized)


def is_complete_memory_statement(text: str) -> bool:
    """Conservative gate for raw FTS5 session-memory storage."""
    normalized = normalize_memory_candidate(text)
    lowered = normalized.lower().rstrip(".!,;:")

    if not lowered:
        return False

    if looks_like_question_or_command(normalized):
        return False

    if _word_count(lowered) < 3:
        return False

    if re.match(r"^i(?:'m| am)\s+\S+", lowered):
        return True

    if any(
        re.match(rf"^i\s+{re.escape(verb)}\s+\S+", lowered)
        for verb in _I_FACT_VERBS
        if verb != "am"
    ):
        return True

    if any(
        re.match(rf"^we\s+{re.escape(verb)}\s+\S+", lowered)
        for verb in _WE_FACT_VERBS
    ):
        return True

    if lowered.startswith(("my ", "our ")):
        for verb in _POSSESSIVE_ASSIGNMENT_VERBS:
            match = re.search(
                rf"\b{re.escape(verb)}\b\s+(.+)$",
                lowered,
            )

            if match and _word_count(match.group(1)) >= 1:
                return True

    return False


def memory_storage_skip_reason(text: str) -> str:
    normalized = normalize_memory_candidate(text)

    if not normalized:
        return "empty"

    if looks_like_personal_fact_fragment(normalized):
        return "personal_fact_fragment"

    if looks_like_question_or_command(normalized):
        return "question_or_command"

    if _word_count(normalized) < 3:
        return "too_short"

    return "incomplete_statement"
