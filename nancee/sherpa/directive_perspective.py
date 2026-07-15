from __future__ import annotations

import re


_ASK_ME_CLAUSE_PATTERN = re.compile(
    r"\bask\s+me\s+(?:if|whether)\s+"
    r"(?P<clause>.+?)(?:[.?!]+)?\s*$",
    flags=re.IGNORECASE,
)

_FIRST_PERSON_PATTERN = re.compile(
    r"\b(?:"
    r"i|i'm|i've|i'd|i'll|me|my|mine"
    r")\b",
    flags=re.IGNORECASE,
)

_SECOND_PERSON_PATTERN = re.compile(
    r"\b(?:"
    r"you|you're|you've|you'd|you'll|your|yours"
    r")\b",
    flags=re.IGNORECASE,
)

_WORD_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9'-]*"
)

_DETERMINERS = {
    "the",
    "my",
    "your",
}

_SOURCE_TO_SPOKEN_DETERMINER = {
    "the": "the",
    "my": "your",
    "your": "my",
}


def _extract_ask_me_clause(user_text: str) -> str:
    match = _ASK_ME_CLAUSE_PATTERN.search(
        str(user_text).strip()
    )

    if match is None:
        return ""

    return (
        match.group("clause")
        .strip()
        .rstrip(".?!")
        .strip()
    )


def _is_single_question(text: str) -> bool:
    probe = str(text).strip()

    probe = probe.rstrip(
        "\"'”’)]}"
    ).rstrip()

    if not probe.endswith("?"):
        return False

    return re.search(
        r"[.!?]",
        probe[:-1],
    ) is None


def _match_case(
    source: str,
    replacement: str,
    *,
    at_sentence_start: bool,
) -> str:
    if (
        at_sentence_start
        and source
        and source[0].isupper()
    ):
        return (
            replacement[0].upper()
            + replacement[1:]
        )

    return replacement


def _replace(
    text: str,
    pattern: str,
    replacement: str,
) -> str:
    return re.sub(
        pattern,
        lambda match: _match_case(
            match.group(0),
            replacement,
            at_sentence_start=not bool(
                match.string[
                    :match.start()
                ].strip()
            ),
        ),
        text,
        flags=re.IGNORECASE,
    )


def _map_first_person_to_second(
    text: str,
) -> str:
    replacements = (
        (r"\bam\s+i\b", "are you"),
        (r"\bwas\s+i\b", "were you"),
        (r"\bi\s+am\b", "you are"),
        (r"\bi\s+was\b", "you were"),
        (r"\bi'm\b", "you're"),
        (r"\bi've\b", "you've"),
        (r"\bi'd\b", "you'd"),
        (r"\bi'll\b", "you'll"),
        (r"\bmine\b", "yours"),
        (r"\bmy\b", "your"),
        (r"\bme\b", "you"),
        (r"\bi\b", "you"),
    )

    repaired = text

    for pattern, replacement in replacements:
        repaired = _replace(
            repaired,
            pattern,
            replacement,
        )

    return repaired


def _map_second_person_to_first(
    text: str,
) -> str:
    replacements = (
        (r"\bare\s+you\b", "am I"),
        (r"\bwere\s+you\b", "was I"),
        (r"\byou\s+are\b", "I am"),
        (r"\byou\s+were\b", "I was"),
        (r"\byou're\b", "I'm"),
        (r"\byou've\b", "I've"),
        (r"\byou'd\b", "I'd"),
        (r"\byou'll\b", "I'll"),
        (r"\byours\b", "mine"),
        (r"\byour\b", "my"),
        (r"\byou\b", "I"),
    )

    repaired = text

    for pattern, replacement in replacements:
        repaired = _replace(
            repaired,
            pattern,
            replacement,
        )

    return repaired


def _find_source_determiner(
    source_tokens: list[str],
    phrase_tokens: list[str],
) -> str | None:
    phrase_length = len(phrase_tokens)

    for index, token in enumerate(source_tokens):
        if token not in _DETERMINERS:
            continue

        following = source_tokens[
            index + 1:
            index + 1 + phrase_length
        ]

        if following == phrase_tokens:
            return token

    return None


def _restore_source_determiners(
    source_clause: str,
    response_text: str,
) -> str:
    source_tokens = [
        match.group(0).lower()
        for match in _WORD_PATTERN.finditer(
            source_clause
        )
    ]

    response_matches = list(
        _WORD_PATTERN.finditer(response_text)
    )

    replacements: list[
        tuple[int, int, str]
    ] = []

    for index, match in enumerate(response_matches):
        output_determiner = match.group(0).lower()

        if output_determiner not in _DETERMINERS:
            continue

        maximum_phrase_length = min(
            4,
            len(response_matches) - index - 1,
        )

        source_determiner = None

        for phrase_length in range(
            maximum_phrase_length,
            0,
            -1,
        ):
            phrase_tokens = [
                response_matches[
                    index + offset
                ].group(0).lower()
                for offset in range(
                    1,
                    phrase_length + 1,
                )
            ]

            source_determiner = (
                _find_source_determiner(
                    source_tokens,
                    phrase_tokens,
                )
            )

            if source_determiner is not None:
                break

        if source_determiner is None:
            continue

        desired_determiner = (
            _SOURCE_TO_SPOKEN_DETERMINER[
                source_determiner
            ]
        )

        if desired_determiner == output_determiner:
            continue

        replacements.append(
            (
                match.start(),
                match.end(),
                _match_case(
                    match.group(0),
                    desired_determiner,
                    at_sentence_start=not bool(
                        response_text[
                            :match.start()
                        ].strip()
                    ),
                ),
            )
        )

    repaired = response_text

    for start, end, replacement in reversed(
        replacements
    ):
        repaired = (
            repaired[:start]
            + replacement
            + repaired[end:]
        )

    return repaired


def repair_directive_perspective(
    user_text: str,
    response_text: str,
) -> tuple[str, bool]:
    """
    Repair speaker perspective for a short ask-me directive.

    This is deliberately narrow:

    - only ask-me commands are eligible;
    - only a single completed question is modified;
    - mixed I/you source clauses are left untouched;
    - articles and possessives are restored from the
      user's original embedded clause.
    """
    original = str(response_text).strip()
    clause = _extract_ask_me_clause(user_text)

    if not original or not clause:
        return original, False

    if not _is_single_question(original):
        return original, False

    source_uses_first_person = bool(
        _FIRST_PERSON_PATTERN.search(clause)
    )

    source_uses_second_person = bool(
        _SECOND_PERSON_PATTERN.search(clause)
    )

    # Both false means no speaker mapping is needed.
    # Both true is ambiguous and should not be rewritten.
    if (
        source_uses_first_person
        == source_uses_second_person
    ):
        return original, False

    if source_uses_first_person:
        repaired = _map_first_person_to_second(
            original
        )
    else:
        repaired = _map_second_person_to_first(
            original
        )

    repaired = _restore_source_determiners(
        clause,
        repaired,
    )

    return repaired, repaired != original
