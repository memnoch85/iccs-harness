import re
from copy import deepcopy

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*")

_STOP_WORDS = {
    "a",
    "about",
    "after",
    "again",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "briefly",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "drive",
    "during",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "here",
    "hers",
    "him",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "me",
    "more",
    "my",
    "ordinary",
    "of",
    "on",
    "or",
    "our",
    "ours",
    "please",
    "relaxed",
    "reply",
    "said",
    "sentence",
    "short",
    "she",
    "so",
    "some",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "they",
    "this",
    "to",
    "conversation",
    "continuing",
    "benchmark",
    "turn",
    "up",
    "us",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
    "yours",
}

_TOKEN_ALIASES = {
    "codes": "code",
    "daughters": "daughter",
    "destinations": "destination",
    "favourite": "favorite",
    "favourites": "favorite",
    "named": "name",
    "names": "name",
    "snacks": "snack",
    "sons": "son",
}


def _canonical_token(token):
    clean_token = token.lower().strip()
    return _TOKEN_ALIASES.get(clean_token, clean_token)


def _tokenize(value):
    tokens = []

    for raw_token in _TOKEN_PATTERN.findall(str(value)):
        token = _canonical_token(raw_token)

        if len(token) <= 1:
            continue

        if token in _STOP_WORDS:
            continue

        tokens.append(token)

    return tokens


def _looks_like_code(token):
    upper_token = token.upper()

    return bool(
        re.fullmatch(r"[A-Z]\d{4}", upper_token)
        or re.fullmatch(r"[A-Z]{2,}-\d+", upper_token)
        or re.fullmatch(r"[A-Z0-9]{6,}", upper_token)
    )


def _token_weight(token):
    if _looks_like_code(token):
        return 5.0

    if len(token) >= 8:
        return 2.0

    return 1.0


class SessionArchive:
    """Stores older turns outside the live Ollama prompt."""

    def __init__(self):
        self._turns = []
        self._next_archive_id = 1

    def add_turns(self, turns):
        added = []

        for turn in turns:
            if not isinstance(turn, dict):
                raise TypeError("Archived turns must be dictionaries.")

            user_text = str(turn.get("user", "")).strip()
            assistant_text = str(turn.get("assistant", "")).strip()

            if not user_text:
                raise ValueError("Archived user text cannot be empty.")

            if not assistant_text:
                raise ValueError("Archived assistant text cannot be empty.")

            archived_turn = {
                "archive_id": self._next_archive_id,
                "user": user_text,
                "assistant": assistant_text,
            }

            self._next_archive_id += 1
            self._turns.append(archived_turn)
            added.append(deepcopy(archived_turn))

        return added

    def retrieve(
        self,
        query,
        *,
        limit=2,
        min_score=2.0,
    ):
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be a positive integer.")

        if limit <= 0:
            raise ValueError("limit must be a positive integer.")

        if min_score < 0:
            raise ValueError("min_score cannot be negative.")

        query_tokens = set(_tokenize(query))

        if not query_tokens:
            return []

        scored_turns = []

        for turn in self._turns:
            user_tokens = set(_tokenize(turn["user"]))
            assistant_tokens = set(_tokenize(turn["assistant"]))

            user_overlap = query_tokens & user_tokens
            assistant_overlap = query_tokens & assistant_tokens

            score = sum(_token_weight(token) * 2.0 for token in user_overlap)
            score += sum(_token_weight(token) for token in assistant_overlap)

            normalized_query = " ".join(_tokenize(query))
            normalized_user = " ".join(_tokenize(turn["user"]))

            if (
                len(query_tokens) >= 2
                and normalized_query
                and normalized_query in normalized_user
            ):
                score += 3.0

            if score < min_score:
                continue

            scored_turns.append(
                {
                    "archive_id": turn["archive_id"],
                    "user": turn["user"],
                    "assistant": turn["assistant"],
                    "score": round(score, 3),
                }
            )

        scored_turns.sort(
            key=lambda item: (
                item["score"],
                item["archive_id"],
            ),
            reverse=True,
        )

        return deepcopy(scored_turns[:limit])

    @staticmethod
    def format_retrieved_context(retrieved_turns):
        if not retrieved_turns:
            return ""

        lines = []

        for number, turn in enumerate(
            retrieved_turns,
            start=1,
        ):
            lines.append(f"Earlier session excerpt {number}:")
            lines.append(f"User said: {turn['user']}")
            lines.append(f"Nancee replied: {turn['assistant']}")

        return "\n".join(lines)

    def get_turns_snapshot(self):
        return deepcopy(self._turns)

    def get_stats(self):
        archive_characters = sum(
            len(turn["user"]) + len(turn["assistant"]) for turn in self._turns
        )

        return {
            "turn_count": len(self._turns),
            "message_count": len(self._turns) * 2,
            "archive_characters": archive_characters,
        }

    def clear(self):
        self._turns.clear()
        self._next_archive_id = 1


def archive_active_memory_if_needed(
    *,
    memory,
    archive,
    max_active_turns,
    max_active_characters,
    keep_recent_turns,
):
    if max_active_turns <= 0:
        raise ValueError("max_active_turns must be positive.")

    if max_active_characters <= 0:
        raise ValueError("max_active_characters must be positive.")

    if keep_recent_turns < 0:
        raise ValueError("keep_recent_turns cannot be negative.")

    if keep_recent_turns >= max_active_turns:
        raise ValueError("keep_recent_turns must be smaller than max_active_turns.")

    stats = memory.get_stats()

    should_archive = (
        stats["turn_count"] > max_active_turns
        or stats["history_characters"] > max_active_characters
    )

    if not should_archive:
        return []

    archived_turns = memory.extract_oldest_turns(
        keep_recent_turns=keep_recent_turns,
    )

    archive.add_turns(archived_turns)
    return archived_turns
