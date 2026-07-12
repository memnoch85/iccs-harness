from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

_STOP_WORDS = {
    "a",
    "about",
    "am",
    "an",
    "are",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "please",
    "remember",
    "should",
    "tell",
    "the",
    "to",
    "was",
    "were",
    "what",
    "whats",
    "when",
    "where",
    "which",
    "who",
    "why",
    "would",
    "you",
}

_KEY_ALIASES = {
    "name": ("name", "identity", "called", "call"),
    "vehicle": (
        "vehicle",
        "car",
        "automobile",
        "drive",
        "driving",
        "color",
    ),
    "car": (
        "vehicle",
        "car",
        "automobile",
        "drive",
        "driving",
        "color",
    ),
    "project": (
        "project",
        "work",
        "working",
        "build",
        "building",
    ),
    "wife": ("wife", "spouse", "partner"),
    "husband": ("husband", "spouse", "partner"),
    "spouse": ("wife", "husband", "spouse", "partner"),
    "mechanic": ("mechanic", "repair", "shop"),
}


@dataclass(frozen=True)
class ProfileFactHit:
    key: str
    value: str
    score: float


def _stringify(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (list, tuple, set)):
        return ", ".join(
            item
            for item in (_stringify(part) for part in value)
            if item
        )

    return str(value).strip()


def _flatten_facts(
    facts: dict[str, Any],
    prefix: str = "",
) -> Iterable[tuple[str, str]]:
    for raw_key, raw_value in facts.items():
        key = str(raw_key).strip()

        if not key:
            continue

        full_key = f"{prefix}.{key}" if prefix else key

        if isinstance(raw_value, dict):
            yield from _flatten_facts(
                raw_value,
                prefix=full_key,
            )
            continue

        value = _stringify(raw_value)

        if value:
            yield full_key, value


def _key_terms(key: str) -> list[str]:
    terms = _TOKEN_PATTERN.findall(str(key).lower())
    expanded = list(terms)

    for term in terms:
        expanded.extend(_KEY_ALIASES.get(term, ()))

    return list(dict.fromkeys(expanded))


def _query_terms(query: str) -> list[str]:
    text = str(query).lower()
    text = text.replace("’", "'")
    text = re.sub(r"\b(nancy|nancee)\b", " ", text)
    text = re.sub(r"\b([a-z]+)'s\b", r"\1", text)

    phrase_replacements = (
        (r"\bwho\s+am\s+i\b", " identity "),
        (r"\bwhat\s+should\s+you\s+call\s+me\b", " identity "),
        (r"\bwhat\s+do\s+i\s+drive\b", " drive "),
        (r"\bwhat\s+am\s+i\s+driving\b", " drive "),
        (r"\bwhat\s+am\s+i\s+working\s+on\b", " project "),
        (r"\bname\s+of\s+my\s+project\b", " project "),
        (r"\bname\s+of\s+my\s+(?:car|vehicle)\b", " vehicle "),
    )

    for pattern, replacement in phrase_replacements:
        text = re.sub(pattern, replacement, text)

    terms = [
        token
        for token in _TOKEN_PATTERN.findall(text)
        if token not in _STOP_WORDS
    ]

    return list(dict.fromkeys(terms))


def _fts_and_query(terms: list[str]) -> str:
    return " AND ".join(
        f'"{term.replace(chr(34), chr(34) * 2)}"'
        for term in terms
    )


class ProfileFactIndex:
    """Small in-memory FTS5 index for stable user-profile facts."""

    def __init__(self, facts: dict[str, Any] | None = None):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE VIRTUAL TABLE profile_fact_fts USING fts5(
                fact_key UNINDEXED,
                fact_value UNINDEXED,
                search_text,
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )

        for key, value in _flatten_facts(facts or {}):
            search_text = " ".join(
                _key_terms(key)
                + _TOKEN_PATTERN.findall(value.lower())
            )

            self.conn.execute(
                """
                INSERT INTO profile_fact_fts(
                    fact_key,
                    fact_value,
                    search_text
                )
                VALUES (?, ?, ?)
                """,
                (key, value, search_text),
            )

        self.conn.commit()

    def count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS count FROM profile_fact_fts"
        ).fetchone()

        return int(row["count"])

    def search(
        self,
        query: str,
        limit: int = 2,
    ) -> list[ProfileFactHit]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        terms = _query_terms(query)

        if not terms:
            return []

        match_query = _fts_and_query(terms)

        rows = self.conn.execute(
            """
            SELECT
                fact_key,
                fact_value,
                bm25(profile_fact_fts) AS score
            FROM profile_fact_fts
            WHERE profile_fact_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (match_query, int(limit)),
        ).fetchall()

        return [
            ProfileFactHit(
                key=str(row["fact_key"]),
                value=str(row["fact_value"]),
                score=float(row["score"]),
            )
            for row in rows
        ]

    @staticmethod
    def format_context(
        hits: list[ProfileFactHit],
        max_characters: int = 240,
    ) -> str:
        if not hits:
            return ""

        if max_characters <= 0:
            raise ValueError("max_characters must be positive")

        header = (
            "Confirmed facts about the human user. "
            "Answer directly and do not mention this fact list.\n"
        )
        lines: list[str] = []

        for hit in hits:
            candidate = f"- {hit.key}: {hit.value}"
            proposed = header + "\n".join(lines + [candidate])

            if len(proposed) > max_characters:
                break

            lines.append(candidate)

        if not lines:
            return ""

        return header + "\n".join(lines)

    def retrieve_context(
        self,
        query: str,
        limit: int = 2,
        max_characters: int = 240,
    ) -> tuple[str, list[ProfileFactHit]]:
        hits = self.search(
            query,
            limit=limit,
        )

        return (
            self.format_context(
                hits,
                max_characters=max_characters,
            ),
            hits,
        )
