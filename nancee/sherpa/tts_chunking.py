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
    "hmm",
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


def is_punctuation_only(text):
    stripped = str(text).strip()

    return (
        bool(stripped)
        and not any(
            character.isalnum()
            for character in stripped
        )
    )


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

    boundary = word_matches[
        split_word_count - 1
    ].end()

    trailing_punctuation = set(
        ".,!?;:'\")]}",
    )

    while (
        boundary < len(buffer)
        and buffer[boundary] in trailing_punctuation
    ):
        boundary += 1

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

        if not (
            LATER_CHUNK_MIN_WORDS
            <= candidate_word_count
            <= LATER_CHUNK_MAX_WORDS
        ):
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

        distance_from_target = abs(
            candidate_word_count
            - LATER_CHUNK_TARGET_WORDS
        )

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

        if (
            chunk
            and not is_punctuation_only(chunk)
        ):
            return chunk, remainder

    # Wait for enough lookahead before forcing a split.
    if len(word_matches) < (
        LATER_CHUNK_MAX_WORDS
        + MIN_REMAINDER_WORDS
    ):
        return None

    selected_word_count = (
        LATER_CHUNK_TARGET_WORDS
    )

    # Search from the target toward the maximum for
    # a word that is not an awkward connector.
    for count in range(
        LATER_CHUNK_TARGET_WORDS,
        LATER_CHUNK_MAX_WORDS + 1,
    ):
        token = re.sub(
            r"[^a-z0-9']",
            "",
            word_matches[
                count - 1
            ].group(0).lower(),
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
    punctuation_pattern = (
        r"[.!?,;:\n]+(?:\s+|$)"
    )

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
