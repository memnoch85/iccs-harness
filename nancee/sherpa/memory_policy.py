from __future__ import annotations

import re


_LEADING_PREFACE = re.compile(
    r"^(?:(?:good morning|good afternoon|good evening|"
    r"so|well|okay|ok|also|and|yeah|yep|yup|uh|um|hmm|"
    r"hello|hi|hey|man|dude|bruh|nancy|nancee)"
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

_POSSESSIVE_RELATION_VERBS = (
    "lives",
    "works",
    "drives",
    "owns",
    "likes",
    "loves",
    "hates",
    "prefers",
    "uses",
)

_POSSESSIVE_FACT_VERBS = (
    _POSSESSIVE_ASSIGNMENT_VERBS
    + _POSSESSIVE_RELATION_VERBS
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

_CONTEXT_DEPENDENT_ANSWER = re.compile(
    r"^(?:i\s+(?:sure\s+)?(?:did|do)|i\s+(?:did|do)\s+not)"
    r"[.! ]*$",
    flags=re.IGNORECASE,
)

_IMPLIED_I_ACTION = re.compile(
    r"^(?:bought|purchased|got|finished|completed|wired|installed|"
    r"built|made|found|lost|parked|left|put|ordered|ate|drank|"
    r"went|met|saw|called|received|returned|submitted|applied)\b",
    flags=re.IGNORECASE,
)


_SIMPLE_FACT_CORRECTION = re.compile(
    r"\b(?:actually\s+)?it\s+was\s+"
    r"(?P<new_value>[^,.!?]{1,80}?)"
    r"\s*,?\s+not\s+"
    r"(?P<old_value>[^,.!?]{1,80})"
    r"(?:[.!?]|$)",
    flags=re.IGNORECASE,
)


_TRAILING_CONVERSATIONAL_CHECKIN = re.compile(
    r"(?:,\s*)?(?:okay|ok|right|alright|you know)\s*\?+$",
    flags=re.IGNORECASE,
)

_SELF_INTRODUCTION_STATEMENT = re.compile(
    r"^(?:this is|my name is)\s+[A-Za-z][A-Za-z'\-]{1,39}[.!]?$",
    flags=re.IGNORECASE,
)

_THIRD_PERSON_FACT_STATEMENTS = (
    re.compile(
        r"^(?:he|she|they)(?:'s|'re|'ll|\s+(?:is|are|was|were|has|have|will|can))"
        r"\s+.+[.!]?$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^(?:his|her|their)\s+.+\s+(?:is|are|was|were|has|have)"
        r"\s+.+[.!]?$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^[A-Z][A-Za-z'\-]{1,39}\s+"
        r"(?:is|was|has|will|can|likes?|lives?|works?|drives?|owns?|prefers?|uses?|talks?)"
        r"\s+.+[.!]?$",
    ),
)


def extract_storable_memory_text(text: str) -> str | None:
    """
    Extract declarative memory clauses from a mixed multi-sentence turn.

    This lets a turn such as:

        His name is Daniel. He's going to talk to you, okay?

    preserve the useful facts without storing the trailing check-in as a
    memory question. The function does not perform route selection.
    """
    raw_text = re.sub(r"\s+", " ", str(text).strip())

    if not raw_text:
        return None

    clauses = re.split(
        r"(?<=[.!?])\s+",
        raw_text,
    )

    accepted: list[str] = []

    for raw_clause in clauses:
        clause = normalize_memory_candidate(raw_clause)

        if not clause:
            continue

        clause = _TRAILING_CONVERSATIONAL_CHECKIN.sub(
            ".",
            clause,
        ).strip()

        if not clause:
            continue

        if clause.endswith("?"):
            continue

        if is_complete_memory_statement(clause):
            accepted.append(clause)
            continue

        if _SELF_INTRODUCTION_STATEMENT.fullmatch(clause):
            accepted.append(clause)
            continue

        if any(
            pattern.fullmatch(clause)
            for pattern in _THIRD_PERSON_FACT_STATEMENTS
        ):
            accepted.append(clause)

    if not accepted:
        return None

    return " ".join(accepted)


def extract_simple_fact_correction(
    text: str,
) -> tuple[str, str] | None:
    """
    Return (new_value, old_value) for a narrow correction shape:

        Actually, it was the power board, not the CAN transceiver.

    This intentionally does not attempt broad language understanding.
    """
    normalized = str(text).strip().replace("’", "'")
    normalized = re.sub(r"\s+", " ", normalized)

    match = _SIMPLE_FACT_CORRECTION.search(normalized)

    if match is None:
        return None

    new_value = match.group("new_value").strip(" ,.!?")
    old_value = match.group("old_value").strip(" ,.!?")

    if not new_value or not old_value:
        return None

    if not (1 <= _word_count(new_value) <= 8):
        return None

    if not (1 <= _word_count(old_value) <= 8):
        return None

    return new_value, old_value


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


_PERSONAL_FACT_QUESTION_PATTERNS = (
    re.compile(
        (
            r"^(?:what|which)\s+"
            r"(?:"
            r"color|colour|name|make|model|brand|"
            r"type|kind|size|year|age|version"
            r")\s+"
            r"(?:is|are)\s+"
            r"(?:my|our)\b"
        ),
        flags=re.IGNORECASE,
    ),
    re.compile(
        (
            r"^what(?:'s| is)\s+the\s+"
            r"(?:"
            r"color|colour|name|make|model|brand|"
            r"type|kind|size|year|age|version"
            r")\s+"
            r"of\s+(?:my|our)\b"
        ),
        flags=re.IGNORECASE,
    ),
)


def looks_like_personal_fact_question(
    text: str,
) -> bool:
    """
    Return True for narrow questions about stable personal facts.

    Examples:
        What color is my helicopter?
        What model is my phone?
        What is the make of my car?

    Diagnostic questions intentionally remain outside this policy.
    """
    normalized = normalize_memory_candidate(
        text
    )

    lowered = re.sub(
        r"\s+",
        " ",
        normalized.lower(),
    ).strip()

    if not lowered:
        return False

    return any(
        pattern.search(lowered)
        for pattern in _PERSONAL_FACT_QUESTION_PATTERNS
    )


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
        for verb in _POSSESSIVE_FACT_VERBS
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

    if _CONTEXT_DEPENDENT_ANSWER.fullmatch(subject_text):
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
        for verb in _POSSESSIVE_FACT_VERBS:
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

    subject_text = _without_temporal_preface(normalized)

    if _LOW_VALUE_FIRST_PERSON.match(subject_text):
        return "low_value_first_person"

    if _CONTEXT_DEPENDENT_ANSWER.fullmatch(subject_text):
        return "context_dependent_answer"

    return "incomplete_statement"

