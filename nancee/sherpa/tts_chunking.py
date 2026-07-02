import re

from config import (
    FIRST_CHUNK_MIN_WORDS,
    MAX_CHUNK_WORDS,
    TARGET_CHUNK_WORDS,
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


def is_filler_preface(text):
    normalized = text.lower().strip()
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

    boundary = word_matches[split_word_count - 1].end()

    chunk = buffer[:boundary].strip()
    remainder = buffer[boundary:].lstrip()

    if not chunk:
        return None

    if is_punctuation_only(chunk):
        return None

    return chunk, remainder


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

    punctuation_pattern = r"[.!?,;:\n]+(?:\s+|$)"

    for match in re.finditer(
        punctuation_pattern,
        buffer,
    ):
        boundary = match.end()
        candidate = buffer[:boundary].strip()
        candidate_words = word_count(candidate)

        if candidate_words < minimum_words:
            continue

        if is_punctuation_only(candidate):
            continue

        if candidate_words <= MAX_CHUNK_WORDS:
            remainder = buffer[boundary:].lstrip()
            return candidate, remainder

        # A nine-word sentence would become 8 + 1.
        # Split it 7 + 2 instead.
        remaining_after_max = candidate_words - MAX_CHUNK_WORDS

        split_word_count = MAX_CHUNK_WORDS

        if remaining_after_max == 1:
            split_word_count -= 1

        return _split_at_word_count(
            buffer,
            split_word_count,
        )

    word_matches = list(
        re.finditer(
            r"\S+",
            buffer,
        )
    )

    # Without punctuation, wait until at least ten words are
    # visible before forcing an eight-word chunk. That leaves
    # at least two words in the buffer.
    if len(word_matches) < (MAX_CHUNK_WORDS + MIN_REMAINDER_WORDS):
        return None

    return _split_at_word_count(
        buffer,
        MAX_CHUNK_WORDS,
    )
