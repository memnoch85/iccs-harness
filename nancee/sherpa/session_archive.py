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
    "nancy",
    "nancee",
    "recall",
    "remember",
    "remind",
    "memory",
    "mentioned",
    "earlier",
    "tell",
    "told",
    "mean",
    "means",
    "kind",
    "type",
    "thing",
    "stuff",
    "currently",
    "capability",
    "capabilities",
    "today",
    "afternoon",
    "good",
    "great",
}

_TOKEN_ALIASES = {
    "automobile": "vehicle",
    "automobiles": "vehicle",
    "car": "vehicle",
    "cars": "vehicle",
    "drive": "vehicle",
    "drives": "vehicle",
    "driving": "vehicle",
    "driven": "vehicle",
    "drove": "vehicle",
    "own": "vehicle",
    "owns": "vehicle",
    "owned": "vehicle",
    "vehicle": "vehicle",
    "vehicles": "vehicle",
    "age": "old",
    "aged": "old",
    "ages": "old",
    "favourite": "favorite",
    "favourites": "favorite",
    "codes": "code",
    "equations": "equation",
    "formulas": "formula",
    "mechanics": "mechanic",
}

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
)

_QUESTION_PHRASES = (
    " do you recall ",
    " can you recall ",
    " do you remember ",
    " can you remember ",
    " what is my ",
    " what's my ",
    " what do i ",
    " who is my ",
    " who's my ",
    " where is ",
    " where's ",
)


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


def _is_question_like(text):
    lowered = re.sub(
        r"\s+",
        " ",
        str(text).strip().lower(),
    )

    lowered = re.sub(
        r"^(nancy|nancee)[,\s]+",
        "",
        lowered,
    )

    if "?" in lowered:
        return True

    if lowered.startswith(_QUESTION_PREFIXES):
        return True

    padded = f" {lowered} "

    return any(phrase in padded for phrase in _QUESTION_PHRASES)


def _normalize_relation_key(value):
    cleaned = str(value).lower()
    cleaned = cleaned.replace("'s", "s")
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    tokens = _tokenize(cleaned)

    if not tokens:
        return ""

    return " ".join(tokens[:5])


def _expand_relation_key(key):
    keys = {key}

    if key.endswith(" name") and key != "name":
        keys.add(key[: -len(" name")].strip())

    return {item for item in keys if item}


def _relation_keys(text):
    lowered = re.sub(
        r"\s+",
        " ",
        str(text).strip().lower(),
    )

    keys = set()

    patterns = (
        r"\bmy\s+([a-z0-9][a-z0-9' -]{0,50}?)\s+(?:is|are|was|were|=)\b",
        r"\bwhat(?:'s|\s+is)\s+my\s+([a-z0-9][a-z0-9' -]{0,50}?)(?:[?.!,]|$)",
        r"\bwho(?:'s|\s+is)\s+my\s+([a-z0-9][a-z0-9' -]{0,50}?)(?:[?.!,]|$)",
        r"\bwhere(?:'s|\s+is)\s+my\s+([a-z0-9][a-z0-9' -]{0,50}?)(?:[?.!,]|$)",
    )

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            lowered,
            flags=re.IGNORECASE,
        ):
            key = _normalize_relation_key(match.group(1))

            if key:
                keys.update(_expand_relation_key(key))

    return keys


def _relation_boost(query, user_text):
    query_keys = _relation_keys(query)
    user_keys = _relation_keys(user_text)

    overlap = query_keys & user_keys

    if not overlap:
        return 0.0

    return 8.0 * len(overlap)


def _word_window(text, query_tokens, max_words):
    words = re.findall(r"\S+", str(text))

    if not words:
        return ""

    canonical_words = [
        _canonical_token(
            re.sub(
                r"[^A-Za-z0-9_-]",
                "",
                word,
            )
        )
        for word in words
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


def _memory_snippet(text, query_tokens, snippet_words):
    clean_text = re.sub(
        r"\s+",
        " ",
        str(text).strip(),
    )

    if len(clean_text) <= 260:
        return clean_text

    return _word_window(
        clean_text,
        query_tokens,
        max(
            snippet_words,
            30,
        ),
    )


class SessionArchive:
    """Bounded in-session recall store.

    Stores completed user turns outside the live Ollama prompt.
    Every request can search this store and inject only the top matches.
    """

    def __init__(self, max_turns=24):
        if isinstance(max_turns, bool) or not isinstance(max_turns, int):
            raise TypeError("max_turns must be a positive integer.")

        if max_turns <= 0:
            raise ValueError("max_turns must be a positive integer.")

        self._max_turns = max_turns
        self._turns = deque()
        self._next_archive_id = 1
        self._last_evicted_count = 0

    def add_turn(self, user_text, assistant_text):
        return self.add_turns(
            [
                {
                    "user": user_text,
                    "assistant": assistant_text,
                }
            ]
        )[0]

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
            f"added={len(added)} "
            f"stored={len(self._turns)} "
            f"evicted={evicted} "
            f"elapsed={elapsed:.6f}s",
            flush=True,
        )

        return added

    def last_evicted_count(self):
        return self._last_evicted_count

    def retrieve(
        self,
        query,
        *,
        limit=3,
        min_score=2.0,
        snippet_words=18,
    ):
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

        if not query_tokens and not _relation_keys(query):
            return []

        scored_turns = []

        for turn in self._turns:
            user_text = turn["user"]
            user_tokens = set(_tokenize(user_text))
            user_overlap = query_tokens & user_tokens

            score = sum(
                _token_weight(token) * 2.0
                for token in user_overlap
            )

            score += _relation_boost(
                query,
                user_text,
            )

            question_like = _is_question_like(user_text)

            if question_like:
                continue

            score += 0.5

            if score < min_score:
                continue

            user_snippet = _memory_snippet(
                user_text,
                query_tokens,
                snippet_words,
            )

            snippet = (
                'The current human user previously said: '
                f'"{user_snippet}"'
            )

            scored_turns.append(
                {
                    "archive_id": turn["archive_id"],
                    "user": turn["user"],
                    "assistant": turn["assistant"],
                    "score": round(score, 3),
                    "question_like": question_like,
                    "snippet": snippet,
                }
            )

        scored_turns.sort(
            key=lambda item: (
                item["score"],
                not item["question_like"],
                item["archive_id"],
            ),
            reverse=True,
        )

        results = deepcopy(scored_turns[:limit])
        elapsed = time.perf_counter() - started

        print(
            "[MEMORY RECALL LOOKUP] "
            f"query={str(query)!r} "
            f"stored={len(self._turns)} "
            f"hits={len(results)} "
            f"ids={[item['archive_id'] for item in results]} "
            f"scores={[item['score'] for item in results]} "
            f"elapsed={elapsed:.6f}s",
            flush=True,
        )

        return results

    @staticmethod
    def format_related_context(
        retrieved_turns,
        *,
        max_characters=650,
    ):
        started = time.perf_counter()

        if not retrieved_turns:
            return ""

        lines = ["RECALLED USER NOTES:"]

        for turn in retrieved_turns:
            snippet = (
                str(
                    turn.get(
                        "snippet",
                        "",
                    )
                )
                .replace(
                    "\n",
                    " ",
                )
                .strip()
            )

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
            len(turn["user"]) + len(turn["assistant"])
            for turn in self._turns
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

# NANCEE generic raw-memory overlay.
# Keep retrieval/scoring intact, but present the stored user fact directly.
def _nancee_format_related_context_raw_memory(self, hits):
    if not hits:
        return ""

    lines = ["RELEVANT USER MEMORY:"]

    for hit in hits:
        user_text = str(
            hit.get("user")
            or hit.get("user_text")
            or ""
        ).strip()

        if user_text:
            lines.append(f"- {user_text}")

    if len(lines) == 1:
        return ""

    return "\n".join(lines)


SessionArchive.format_related_context = _nancee_format_related_context_raw_memory

# NANCEE generic raw-memory overlay v2.
# Accepts max_characters because nancee_chat.py passes it.
def _nancee_format_related_context_raw_memory_v2(
    self,
    hits,
    max_characters=None,
    *args,
    **kwargs,
):
    if not hits:
        return ""

    lines = ["RELEVANT USER MEMORY:"]

    for hit in hits:
        user_text = str(
            hit.get("user")
            or hit.get("user_text")
            or ""
        ).strip()

        if user_text:
            lines.append(f"- {user_text}")

    if len(lines) == 1:
        return ""

    context = "\n".join(lines)

    if max_characters and len(context) > max_characters:
        return context[:max_characters].rstrip()

    return context


SessionArchive.format_related_context = _nancee_format_related_context_raw_memory_v2
