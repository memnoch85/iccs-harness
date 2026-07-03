import re
import time
from collections import deque
from copy import deepcopy

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*")

_STOP_WORDS = {
    "a",
    "about",
    "again",
    "all",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "just",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "so",
    "that",
    "the",
    "this",
    "to",
    "up",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}

_TOKEN_ALIASES = {
    "bench": "finch",
    "favourite": "favorite",
    "favourites": "favorite",
    "codes": "code",
    "equations": "equation",
    "formulas": "formula",
    "mechanics": "mechanic",
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


def _word_window(text, query_tokens, max_words):
    words = re.findall(r"\S+", str(text))
    if not words:
        return ""

    canonical_words = [
        _canonical_token(re.sub(r"[^A-Za-z0-9_-]", "", word)) for word in words
    ]

    match_index = None
    for index, token in enumerate(canonical_words):
        if token in query_tokens:
            match_index = index
            break

    if match_index is None:
        selected = words[:max_words]
        suffix = "..." if len(words) > max_words else ""
        return " ".join(selected).strip() + suffix

    before = max_words // 2
    start = max(0, match_index - before)
    end = min(len(words), start + max_words)
    start = max(0, end - max_words)

    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(words) else ""
    return prefix + " ".join(words[start:end]).strip() + suffix


class SessionArchive:
    """Stores older turns outside the live Ollama prompt and recalls tiny snippets."""

    def __init__(self, max_turns=24):
        if isinstance(max_turns, bool) or not isinstance(max_turns, int):
            raise TypeError("max_turns must be a positive integer.")
        if max_turns <= 0:
            raise ValueError("max_turns must be a positive integer.")

        self._max_turns = max_turns
        self._turns = deque()
        self._next_archive_id = 1
        self._last_evicted_count = 0

    def add_turns(self, turns):
        started = time.perf_counter()
        added = []
        evicted = 0

        for turn in turns:
            if not isinstance(turn, dict):
                raise TypeError("Archived turns must be dictionaries.")

            user_text = str(turn.get("user", "")).strip()
            assistant_text = str(turn.get("assistant", "")).strip()

            if not user_text:
                raise ValueError("Archived user text cannot be empty.")
            if not assistant_text:
                raise ValueError("Archived assistant text cannot be empty.")

            while len(self._turns) >= self._max_turns:
                self._turns.popleft()
                evicted += 1

            archived_turn = {
                "archive_id": self._next_archive_id,
                "user": user_text,
                "assistant": assistant_text,
            }

            self._next_archive_id += 1
            self._turns.append(archived_turn)
            added.append(deepcopy(archived_turn))

        self._last_evicted_count = evicted
        elapsed = time.perf_counter() - started

        print(
            "[MEMORY INDEX ADD] "
            f"added={len(added)} stored={len(self._turns)} "
            f"evicted={evicted} elapsed={elapsed:.6f}s",
            flush=True,
        )

        return added

    def last_evicted_count(self):
        return self._last_evicted_count

    def retrieve(self, query, *, limit=3, min_score=2.0, snippet_words=18):
        started = time.perf_counter()

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be a positive integer.")
        if limit <= 0:
            raise ValueError("limit must be a positive integer.")
        if min_score < 0:
            raise ValueError("min_score cannot be negative.")
        if snippet_words <= 0:
            raise ValueError("snippet_words must be positive.")

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

            if score < min_score:
                continue

            user_snippet = _word_window(turn["user"], query_tokens, snippet_words)
            assistant_snippet = _word_window(
                turn["assistant"], query_tokens, snippet_words
            )

            snippet = f"User: {user_snippet} | Nancee: {assistant_snippet}"

            scored_turns.append(
                {
                    "archive_id": turn["archive_id"],
                    "user": turn["user"],
                    "assistant": turn["assistant"],
                    "score": round(score, 3),
                    "snippet": snippet,
                }
            )

        scored_turns.sort(
            key=lambda item: (item["score"], item["archive_id"]),
            reverse=True,
        )

        results = deepcopy(scored_turns[:limit])
        elapsed = time.perf_counter() - started

        print(
            "[MEMORY RECALL LOOKUP] "
            f"query={str(query)!r} archived={len(self._turns)} "
            f"hits={len(results)} ids={[item['archive_id'] for item in results]} "
            f"scores={[item['score'] for item in results]} "
            f"elapsed={elapsed:.6f}s",
            flush=True,
        )

        return results

    @staticmethod
    def format_related_context(retrieved_turns, *, max_characters=650):
        started = time.perf_counter()

        if not retrieved_turns:
            return ""

        lines = ["RELATED SESSION MEMORY:"]

        for turn in retrieved_turns:
            snippet = str(turn.get("snippet", "")).replace("\n", " ").strip()
            if not snippet:
                continue

            line = f"- {snippet}"
            candidate = "\n".join(lines + [line])

            if len(candidate) <= max_characters:
                lines.append(line)
                continue

            remaining = max_characters - len("\n".join(lines)) - 4
            if len(lines) == 1 and remaining > 25:
                lines.append(line[:remaining].rstrip() + "...")
            break

        if len(lines) == 1:
            return ""

        context = "\n".join(lines)
        elapsed = time.perf_counter() - started

        print(
            f"[MEMORY RECALL CONTEXT] characters={len(context)} elapsed={elapsed:.6f}s",
            flush=True,
        )

        return context

    def get_turns_snapshot(self):
        return deepcopy(list(self._turns))

    def get_stats(self):
        archive_characters = sum(
            len(turn["user"]) + len(turn["assistant"]) for turn in self._turns
        )

        return {
            "max_turns": self._max_turns,
            "turn_count": len(self._turns),
            "message_count": len(self._turns) * 2,
            "archive_characters": archive_characters,
        }

    def clear(self):
        self._turns.clear()
        self._next_archive_id = 1
        self._last_evicted_count = 0


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

    archived_turns = memory.extract_oldest_turns(keep_recent_turns=keep_recent_turns)
    archive.add_turns(archived_turns)
    return archived_turns
