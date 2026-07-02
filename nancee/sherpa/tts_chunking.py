from __future__ import annotations

import re

from config import (
    FIRST_CHUNK_MIN_WORDS,
    MAX_CHUNK_WORDS,
    TARGET_CHUNK_WORDS,
)


def is_punctuation_only(text):
    stripped = text.strip()

    return bool(stripped) and not any(character.isalnum() for character in stripped)


def word_count(text):
    return len(
        re.findall(
            r"\S+",
            text,
        )
    )


def extract_tts_chunk(
    buffer,
    is_first,
):
    stripped = buffer.strip()

    if not stripped:
        return None

    if is_punctuation_only(stripped):
        return None

    minimum_words = FIRST_CHUNK_MIN_WORDS if is_first else TARGET_CHUNK_WORDS

    # Prefer a natural punctuation boundary once the configured
    # minimum word count has been reached.
    punctuation_pattern = r"[.!?,;:\n]+(?:\s+|$)"

    for match in re.finditer(
        punctuation_pattern,
        buffer,
    ):
        boundary = match.end()
        candidate = buffer[:boundary].strip()

        if word_count(candidate) < minimum_words:
            continue

        if is_punctuation_only(candidate):
            continue

        remainder = buffer[boundary:].lstrip()

        return candidate, remainder

    # Force a chunk at eight complete words if no suitable
    # punctuation boundary has appeared.
    word_matches = list(
        re.finditer(
            r"\S+",
            buffer,
        )
    )

    if len(word_matches) < MAX_CHUNK_WORDS:
        return None

    maximum_word = word_matches[MAX_CHUNK_WORDS - 1]

    maximum_word_is_complete = len(
        word_matches
    ) > MAX_CHUNK_WORDS or maximum_word.end() < len(buffer)

    if not maximum_word_is_complete:
        return None

    boundary = maximum_word.end()
    chunk = buffer[:boundary].strip()
    remainder = buffer[boundary:].lstrip()

    if not chunk:
        return None

    if is_punctuation_only(chunk):
        return None

    return chunk, remainder
