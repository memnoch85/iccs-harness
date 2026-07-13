from __future__ import annotations

import re
from typing import Iterable, Protocol


class ProfileHitLike(Protocol):
    key: str
    value: str


_WORD = re.compile(r"[a-z0-9']+")
_MEMORY_MISS_PATTERN = re.compile(
    r"\b(?:do not|don't|cannot|can't)\s+(?:remember|recall)\b",
    flags=re.IGNORECASE,
)
_MEMORY_QUOTE_PATTERN = re.compile(
    r'-\s*User said:\s*"([^"]+)"',
    flags=re.IGNORECASE,
)

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
    "did", "do", "does", "for", "from", "had", "has", "have", "he",
    "her", "hers", "him", "his", "i", "in", "is", "it", "its", "me",
    "my", "of", "on", "or", "our", "ours", "she", "that", "the",
    "their", "theirs", "them", "they", "this", "to", "was", "we",
    "were", "what", "when", "where", "which", "who", "why", "with",
    "you", "your", "yours", "said", "user", "human", "memory", "s",
}

_CANONICAL = {
    "bought": "buy",
    "buying": "buy",
    "purchased": "buy",
    "purchase": "buy",
    "purchasing": "buy",
    "got": "get",
    "getting": "get",
    "drove": "drive",
    "driving": "drive",
    "finished": "finish",
    "completed": "finish",
    "wiring": "wire",
    "wired": "wire",
}


def first_sentence_only(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()

    if not cleaned:
        return ""

    match = re.search(r"[.!?](?:\s|$)", cleaned)

    if match:
        return cleaned[: match.end()].strip()

    return cleaned


def _normalized_words(text: str) -> list[str]:
    return _WORD.findall(str(text).lower())


def _contains_phrase(answer: str, value: str) -> bool:
    answer_words = _normalized_words(answer)
    value_words = _normalized_words(value)

    if not value_words:
        return False

    answer_text = " ".join(answer_words)
    value_text = " ".join(value_words)
    return value_text in answer_text


def _content_tokens(text: str) -> set[str]:
    tokens = set()

    for token in _normalized_words(text):
        token = token.strip("'")
        token = _CANONICAL.get(token, token)

        if len(token) < 3 or token in _STOPWORDS:
            continue

        tokens.add(token)

    return tokens


def _memory_source_text(retrieved_context: str) -> str:
    quoted = _MEMORY_QUOTE_PATTERN.findall(str(retrieved_context))

    if quoted:
        return " ".join(quoted)

    return str(retrieved_context)


def session_memory_response_is_grounded(
    answer: str,
    retrieved_context: str,
) -> bool:
    if not str(retrieved_context).strip():
        return True

    answer_tokens = _content_tokens(answer)
    memory_tokens = _content_tokens(_memory_source_text(retrieved_context))

    if not answer_tokens or not memory_tokens:
        return False

    return bool(answer_tokens & memory_tokens)


def profile_response_matches(
    answer: str,
    hits: Iterable[ProfileHitLike],
) -> bool:
    hit_list = list(hits)

    if not hit_list:
        return True

    for hit in hit_list:
        key_tail = str(hit.key).split(".")[-1].lower()
        value = str(hit.value).strip()

        if key_tail in {"name", "vehicle", "car"}:
            if not _contains_phrase(answer, value):
                return False
            continue

        value_words = _normalized_words(value)
        answer_words = set(_normalized_words(answer))

        if not value_words:
            return False

        required = value_words[:1]

        if not all(word in answer_words for word in required):
            return False

    return True


def profile_fallback(hits: Iterable[ProfileHitLike]) -> str:
    hit_list = list(hits)

    if not hit_list:
        return "I don't remember that yet."

    hit = hit_list[0]
    key_tail = str(hit.key).split(".")[-1].replace("_", " ").lower()
    value = str(hit.value).strip()

    if key_tail == "name":
        return f"You're {value}."

    if key_tail in {"vehicle", "car"}:
        article = "an" if value[:1].lower() in "aeiou" else "a"
        return f"You drive {article} {value}."

    if key_tail == "project":
        return f"Your project is {value}."

    return f"Your {key_tail} is {value}."


def prepare_authoritative_response(
    text: str,
    *,
    profile_hits: Iterable[ProfileHitLike],
    fact_miss: bool,
    retrieved_context: str = "",
) -> tuple[str, str]:
    """Trim and validate a fact-backed answer before TTS or history storage."""
    cleaned = first_sentence_only(text)
    hits = list(profile_hits)

    if fact_miss:
        if not _MEMORY_MISS_PATTERN.search(cleaned):
            return "I don't remember that yet.", "fact_miss_fallback"

        return cleaned, "fact_miss_accepted"

    if hits and not profile_response_matches(cleaned, hits):
        return profile_fallback(hits), "profile_fallback"

    if retrieved_context and not session_memory_response_is_grounded(
        cleaned,
        retrieved_context,
    ):
        return (
            "I don't remember that clearly enough.",
            "memory_grounding_fallback",
        )

    return cleaned, "accepted"

