from __future__ import annotations

import re


_LEADING_PREFACE = re.compile(
    r"^(?:(?:good morning|good afternoon|good evening|"
    r"so|well|okay|ok|also|and|hello|hi|hey|nancy|nancee)"
    r"\b[\s,!.:;\-]*)+",
    flags=re.IGNORECASE,
)

_TEMPORAL_PREFACE = re.compile(
    r"^(?:(?:today|yesterday|recently|earlier|last night|"
    r"this morning|this afternoon|this evening|tonight)"
    r"\b[\s,!.:;\-]*)+",
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

_LOW_VALUE_FIRST_PERSON = re.compile(
    r"^(?:"
    r"i\s+(?:think|guess|mean|wonder|hope)\b|"
    r"i(?:'m| am)\s+not\s+sure\b|"
    r"i\s+(?:do not|don't)\s+know\b|"
    r"i\s+(?:need|want)\s+you\s+to\b"
    r")",
    flags=re.IGNORECASE,
)

_IMPLIED_I_ACTION = re.compile(
    r"^(?:bought|purchased|got|finished|completed|wired|installed|"
    r"built|made|found|lost|parked|left|put|ordered|ate|drank|"
    r"went|met|saw|called|received|returned|submitted|applied)\b",
    flags=re.IGNORECASE,
)


def normalize_memory_candidate(text: str) -> str:
    normalized = str(text).strip().replace("’", "'")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = _LEADING_PREFACE.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _without_temporal_preface(text: str) -> str:
    return _TEMPORAL_PREFACE.sub("", text).strip()


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
    """Conservative raw-memory gate without a large verb whitelist."""
    normalized = normalize_memory_candidate(text)
    lowered = normalized.lower().rstrip(".!,;:")

    if not lowered:
        return False

    if looks_like_question_or_command(normalized):
        return False

    if _word_count(lowered) < 3:
        return False

    subject_text = _without_temporal_preface(lowered)

    if _LOW_VALUE_FIRST_PERSON.match(subject_text):
        return False

    # A first-person clause with at least a subject, action/state, and value.
    # We store the raw utterance; FTS5 decides later whether it is relevant.
    if re.match(r"^i(?:'m| am)\s+\S+", subject_text):
        return True

    if re.match(r"^i\s+\S+\s+\S+", subject_text):
        return True

    if re.match(r"^we(?:'re| are)\s+\S+", subject_text):
        return True

    if re.match(r"^we\s+\S+\s+\S+", subject_text):
        return True

    if subject_text.startswith(("my ", "our ")):
        for verb in _POSSESSIVE_ASSIGNMENT_VERBS:
            match = re.search(
                rf"\b{re.escape(verb)}\b\s+(.+)$",
                subject_text,
            )

            if match and _word_count(match.group(1)) >= 1:
                return True

    # Whisper sometimes drops the leading "I" but preserves an unmistakable
    # completed-action statement: "Bought a blue backpack at Macy's."
    if _IMPLIED_I_ACTION.match(subject_text) and _word_count(subject_text) >= 4:
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

    if _LOW_VALUE_FIRST_PERSON.match(_without_temporal_preface(normalized)):
        return "low_value_first_person"

    return "incomplete_statement"

