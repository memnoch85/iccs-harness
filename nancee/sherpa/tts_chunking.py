import re

from config import (
    FIRST_CHUNK_MAX_WORDS,
    FIRST_CHUNK_MIN_WORDS,
    LATER_CHUNK_MAX_WORDS,
    LATER_CHUNK_MIN_WORDS,
    LATER_CHUNK_TARGET_WORDS,
)

MIN_REMAINDER_WORDS = 2

FILLER_PREFACES = {
    "actually",
    "alright",
    "anyway",
    "hang on",
    "hum",
    "let me think",
    "let's see",
    "ok",
    "okay",
    "right",
    "so",
    "sure",
    "uh",
    "um",
    "well",
    "you know",
}

_WEAK_CHUNK_ENDINGS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

# Expressions that should be spoken as one semantic unit.
# Forced word-count splitting must not divide these pairs.
_PROTECTED_SPLIT_PAIRS = {
    ("check", "out"),
    ("figure", "out"),
    ("find", "out"),
    ("log", "in"),
    ("mix", "up"),
    ("power", "up"),
    ("set", "up"),
    ("shut", "down"),
    ("sign", "in"),
    ("turn", "off"),
    ("turn", "on"),
}

_PROTECTED_PAIR_PREFIXES = {
    left_word
    for left_word, _right_word
    in _PROTECTED_SPLIT_PAIRS
}


def _normalize_boundary_word(text):
    return re.sub(
        r"[^a-z0-9']",
        "",
        str(text).lower(),
    )


def is_punctuation_only(text):
    stripped = str(text).strip()

    return bool(stripped) and not any(character.isalnum() for character in stripped)


def word_count(text):
    return len(
        re.findall(
            r"\S+",
            str(text),
        )
    )


def is_filler_preface(text):
    normalized = str(text).lower().strip()

    normalized = re.sub(
        r"[*_`]",
        "",
        normalized,
    )

    normalized = re.sub(
        r"[^a-z0-9'\s]",
        "",
        normalized,
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()

    return normalized in FILLER_PREFACES


def _split_at_word_count(
    buffer,
    split_word_count,
):
    word_matches = list(
        re.finditer(
            r"\S+",
            buffer,
        )
    )

    if len(word_matches) < split_word_count:
        return None

    # Protect two-word expressions from forced chunk boundaries.
    #
    # Example:
    #   "Apologies for that mix up"
    #
    # becomes:
    #   "Apologies for that"
    #   "mix up"
    while (
        split_word_count > 1
        and split_word_count < len(word_matches)
    ):
        left_word = _normalize_boundary_word(
            word_matches[
                split_word_count - 1
            ].group(0)
        )

        right_word = _normalize_boundary_word(
            word_matches[
                split_word_count
            ].group(0)
        )

        if (
            left_word,
            right_word,
        ) not in _PROTECTED_SPLIT_PAIRS:
            break

        split_word_count -= 1

    # A streamed buffer may temporarily end after "mix ".
    # Wait for the next word before deciding whether this is
    # the protected phrase "mix up".
    if split_word_count == len(word_matches):
        final_word = _normalize_boundary_word(
            word_matches[
                split_word_count - 1
            ].group(0)
        )

        trimmed_buffer = buffer.rstrip()

        punctuation_probe = trimmed_buffer.rstrip(
            "\"')]}",
        )

        has_terminal_punctuation = (
            bool(punctuation_probe)
            and punctuation_probe[-1]
            in ".,!?;:"
        )

        if (
            final_word in _PROTECTED_PAIR_PREFIXES
            and not has_terminal_punctuation
        ):
            return None

    boundary = word_matches[
        split_word_count - 1
    ].end()

    trailing_punctuation = set(
        ".,!?;:'\")]}",
    )

    while (
        boundary < len(buffer)
        and buffer[boundary]
        in trailing_punctuation
    ):
        boundary += 1

    trimmed_buffer = buffer.rstrip()

    boundary_is_visible_end = (
        boundary >= len(trimmed_buffer)
    )

    has_trailing_whitespace = (
        bool(buffer)
        and buffer[-1].isspace()
    )

    # Remove closing quotes or brackets before checking
    # whether punctuation confirmed the final word.
    punctuation_probe = trimmed_buffer.rstrip(
        "\"')]}",
    )

    has_terminal_punctuation = (
        bool(punctuation_probe)
        and punctuation_probe[-1]
        in ".,!?;:"
    )

    # The end of a streamed buffer does not prove the final
    # visible word is complete. For example, the current
    # buffer may contain "Your name is N" while the next
    # token completes it as "Nancee".
    if (
        boundary_is_visible_end
        and not has_trailing_whitespace
        and not has_terminal_punctuation
    ):
        return None

    chunk = buffer[:boundary].strip()
    remainder = buffer[boundary:].lstrip()

    if not chunk:
        return None

    if is_punctuation_only(chunk):
        return None

    return chunk, remainder


def _extract_semantic_later_chunk(buffer):
    word_matches = list(
        re.finditer(
            r"\S+",
            buffer,
        )
    )

    candidates = []

    # Prefer punctuation boundaries between the configured
    # minimum and maximum later-chunk sizes.
    for match in re.finditer(
        r"""[.!?,;:]+(?:["')\]]+)?(?:\s+|$)""",
        buffer,
    ):
        boundary = match.end()

        candidate_word_count = word_count(
            buffer[:boundary],
        )

        if not (LATER_CHUNK_MIN_WORDS <= candidate_word_count <= LATER_CHUNK_MAX_WORDS):
            continue

        # Sentence endings rank ahead of commas,
        # semicolons, and colons.
        strength = (
            0
            if re.search(
                r"[.!?]",
                match.group(0),
            )
            else 1
        )

        distance_from_target = abs(candidate_word_count - LATER_CHUNK_TARGET_WORDS)

        candidates.append(
            (
                strength,
                distance_from_target,
                boundary,
            )
        )

    if candidates:
        candidates.sort()

        boundary = candidates[0][2]

        chunk = buffer[:boundary].strip()
        remainder = buffer[boundary:].lstrip()

        if chunk and not is_punctuation_only(chunk):
            return chunk, remainder

    # Wait for enough lookahead before forcing a split.
    if len(word_matches) < (LATER_CHUNK_MAX_WORDS + MIN_REMAINDER_WORDS):
        return None

    selected_word_count = LATER_CHUNK_TARGET_WORDS

    # Search from the target toward the maximum for
    # a word that is not an awkward connector.
    for count in range(
        LATER_CHUNK_TARGET_WORDS,
        LATER_CHUNK_MAX_WORDS + 1,
    ):
        token = re.sub(
            r"[^a-z0-9']",
            "",
            word_matches[count - 1].group(0).lower(),
        )

        if token not in _WEAK_CHUNK_ENDINGS:
            selected_word_count = count
            break

    return _split_at_word_count(
        buffer,
        selected_word_count,
    )


def extract_tts_chunk(
    buffer,
    is_first,
):
    stripped = str(buffer).strip()

    if not stripped:
        return None

    if is_punctuation_only(stripped):
        return None

    # Later chunks use only the semantic boundary logic.
    if not is_first:
        return _extract_semantic_later_chunk(
            buffer,
        )

    # Everything below this point is first-chunk logic.
    punctuation_pattern = r"[.!?,;:\n]+(?:\s+|$)"

    for match in re.finditer(
        punctuation_pattern,
        buffer,
    ):
        boundary = match.end()
        candidate = buffer[:boundary].strip()
        candidate_words = word_count(candidate)

        if candidate_words < FIRST_CHUNK_MIN_WORDS:
            continue

        if is_punctuation_only(candidate):
            continue

        if candidate_words > FIRST_CHUNK_MAX_WORDS:
            return _split_at_word_count(
                buffer,
                FIRST_CHUNK_MAX_WORDS,
            )

        remainder = buffer[boundary:].lstrip()

        return candidate, remainder

    # Start TTS quickly even if punctuation has not
    # arrived yet.
    first_words = list(
        re.finditer(
            r"\S+",
            buffer,
        )
    )

    if len(first_words) >= FIRST_CHUNK_MAX_WORDS:
        return _split_at_word_count(
            buffer,
            FIRST_CHUNK_MAX_WORDS,
        )

    return None
