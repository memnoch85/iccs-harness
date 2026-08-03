from __future__ import annotations

import re

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






def prepare_authoritative_response(
    text: str,
    *,
    fact_miss: bool,
    retrieved_context: str = "",
) -> tuple[str, str]:
    """Trim and validate a fact-backed answer before TTS or history storage."""
    cleaned = first_sentence_only(text)
    if fact_miss:
        if not _MEMORY_MISS_PATTERN.search(cleaned):
            return "I don't remember that yet.", "fact_miss_fallback"

        return cleaned, "fact_miss_accepted"


    if retrieved_context and not session_memory_response_is_grounded(
        cleaned,
        retrieved_context,
    ):
        return (
            "I don't remember that clearly enough.",
            "memory_grounding_fallback",
        )

    return cleaned, "accepted"
