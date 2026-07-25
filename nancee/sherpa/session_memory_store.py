import re
import sqlite3
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "im",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "would",
    "you",
    "your",
    "nancy",
    "nancee",
    "hey",
    "hello",
    "hi",
    "okay",
    "ok",
    "so",
    "well",
    "just",
    "remember",
    "recall",
    "should",
}

FILLER_ONLY = {"ok", "okay", "yes", "no", "sure", "thanks", "thank you", "bye"}

OVERLAP_TOKEN_CANONICAL = {
    "bought": "buy",
    "buying": "buy",
    "completed": "complete",
    "completing": "complete",
    "drove": "drive",
    "driving": "drive",
    "finished": "finish",
    "finishing": "finish",
    "purchased": "buy",
    "purchasing": "buy",
    "wired": "wire",
    "wiring": "wire",
}

QUERY_TOKEN_EXPANSIONS = {
    "buy": ("buy", "bought", "purchase", "purchased"),
    "bought": ("buy", "bought", "purchase", "purchased"),
    "purchase": ("buy", "bought", "purchase", "purchased"),
    "purchased": ("buy", "bought", "purchase", "purchased"),
    "drive": ("drive", "drove", "driving"),
    "drove": ("drive", "drove", "driving"),
    "driving": ("drive", "drove", "driving"),
    "eat": ("eat", "ate"),
    "ate": ("eat", "ate"),
    "go": ("go", "went"),
    "went": ("go", "went"),
}


@dataclass
class MemoryHit:
    id: int
    raw_text: str
    search_text: str
    bm25_score: float
    created_ts: float
    turn_id: Optional[int]


def tokenize(text: str) -> List[str]:
    text = str(text).lower().replace("'", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [
        tok
        for tok in text.split()
        if len(tok) >= 2 and tok not in STOPWORDS
    ]


def _overlap_tokens(text: str) -> set[str]:
    return {
        OVERLAP_TOKEN_CANONICAL.get(token, token)
        for token in tokenize(text)
    }


def meaningful_token_overlap_count(
    query_text: str,
    memory_text: str,
) -> int:
    query_tokens = _overlap_tokens(query_text)
    memory_tokens = _overlap_tokens(memory_text)
    return len(query_tokens & memory_tokens)


def filter_memory_hits_by_overlap(
    query_text: str,
    hits,
    minimum_overlap: int = 2,
    allow_weak_match: bool = False,
):
    if minimum_overlap <= 0:
        raise ValueError("minimum_overlap must be positive")

    hit_list = list(hits or [])

    if allow_weak_match:
        return hit_list

    filtered = []

    for hit in hit_list:
        if isinstance(hit, dict):
            memory_text = (
                hit.get("search_text")
                or hit.get("user")
                or hit.get("user_text")
                or ""
            )
        else:
            memory_text = (
                getattr(hit, "search_text", "")
                or getattr(hit, "raw_text", "")
            )

        if meaningful_token_overlap_count(
            query_text,
            memory_text,
        ) >= minimum_overlap:
            filtered.append(hit)

    return filtered


def normalize_for_search(text: str) -> str:
    # FTS5-only: no aliases, no semantic expansion.
    return " ".join(tokenize(text))


def make_fts_query(text: str) -> str:
    tokens = tokenize(text)

    if not tokens:
        return ""

    safe = []
    seen = set()

    for token in tokens:
        candidates = QUERY_TOKEN_EXPANSIONS.get(
            token,
            (token,),
        )

        for candidate in candidates:
            clean_candidate = re.sub(
                r"[^a-z0-9]",
                "",
                candidate,
            )

            if clean_candidate and clean_candidate not in seen:
                seen.add(clean_candidate)
                safe.append(clean_candidate)

    return " OR ".join(safe)


def should_store_memory(raw_text: str) -> bool:
    raw = str(raw_text).strip()
    if not raw:
        return False
    if raw.lower() in FILLER_ONLY:
        return False
    return len(tokenize(raw)) >= 2


def format_memory_overlay(
    hits: List[MemoryHit],
    max_characters: Optional[int] = None,
) -> str:
    if not hits:
        return ""

    lines = [
        "Confirmed user memory. In quotes, I/me/my means the human user; "
        "answer as you/your.",
    ]

    seen = set()

    for hit in hits:
        raw = str(hit.raw_text).strip()

        if not raw or raw.lower() in seen:
            continue

        seen.add(raw.lower())
        escaped = raw.replace('"', "'")
        lines.append(f'- User said: "{escaped}"')

    text = "\n".join(lines)

    if max_characters and len(text) > max_characters:
        text = text[:max_characters].rstrip()

    return text

def _best_fuzzy_word_span(
    raw_text: str,
    target_text: str,
) -> tuple[int, int, float] | None:
    raw = str(raw_text)
    target = re.sub(
        r"\s+",
        " ",
        str(target_text).strip().lower(),
    )

    if not raw or not target:
        return None

    word_matches = list(
        re.finditer(
            r"[A-Za-z0-9']+",
            raw,
        )
    )
    target_words = re.findall(
        r"[a-z0-9']+",
        target,
    )

    if not word_matches or not target_words:
        return None

    target_count = len(target_words)
    minimum_window = max(
        1,
        target_count - 1,
    )
    maximum_window = min(
        len(word_matches),
        target_count + 1,
    )

    best = None

    for window_size in range(
        minimum_window,
        maximum_window + 1,
    ):
        for start_index in range(
            0,
            len(word_matches) - window_size + 1,
        ):
            end_index = start_index + window_size - 1
            start = word_matches[start_index].start()
            end = word_matches[end_index].end()
            candidate = raw[start:end].lower()

            score = SequenceMatcher(
                None,
                target,
                candidate,
            ).ratio()

            if best is None or score > best[2]:
                best = (
                    start,
                    end,
                    score,
                )

    return best


class SessionMemoryStore:
    def __init__(self, max_memories: int = 384, db_path: Optional[str] = None):
        self.max_memories = int(max_memories)
        self.conn = sqlite3.connect(db_path or ":memory:")
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                raw_text UNINDEXED,
                search_text,
                created_ts UNINDEXED,
                turn_id UNINDEXED,
                tokenize='porter unicode61'
            )
        """)
        self.conn.commit()

    def add_memory(self, raw_text: str, turn_id: Optional[int] = None) -> Optional[int]:
        if not should_store_memory(raw_text):
            return None
        search_text = normalize_for_search(raw_text)
        if not search_text:
            return None
        now = time.time()
        cur = self.conn.execute(
            """INSERT INTO memory_fts(raw_text, search_text, created_ts, turn_id)
               VALUES (?, ?, ?, ?)""",
            (
                str(raw_text).strip(),
                search_text,
                now,
                "" if turn_id is None else str(turn_id),
            ),
        )
        self.conn.commit()
        self._evict_old()
        return int(cur.lastrowid)

    def _evict_old(self) -> None:
        if self.max_memories <= 0:
            return
        count = int(
            self.conn.execute("SELECT COUNT(*) AS c FROM memory_fts").fetchone()["c"]
        )
        if count <= self.max_memories:
            return
        extra = count - self.max_memories
        rows = self.conn.execute(
            "SELECT rowid FROM memory_fts ORDER BY created_ts ASC LIMIT ?",
            (extra,),
        ).fetchall()
        for row in rows:
            self.conn.execute(
                "DELETE FROM memory_fts WHERE rowid = ?", (int(row["rowid"]),)
            )
        self.conn.commit()

    def search_memory(self, query: str, limit: int = 3) -> List[MemoryHit]:
        match_query = make_fts_query(query)
        if not match_query:
            return []
        rows = self.conn.execute(
            """
            SELECT rowid, raw_text, search_text, created_ts, turn_id,
                   bm25(memory_fts) AS bm25_score
            FROM memory_fts
            WHERE memory_fts MATCH ?
            ORDER BY bm25_score ASC, created_ts DESC, rowid DESC
            LIMIT ?
            """,
            (match_query, int(limit)),
        ).fetchall()
        hits = []
        for row in rows:
            turn_id = row["turn_id"]
            hits.append(
                MemoryHit(
                    id=int(row["rowid"]),
                    raw_text=row["raw_text"],
                    search_text=row["search_text"],
                    bm25_score=float(row["bm25_score"]),
                    created_ts=float(row["created_ts"]),
                    turn_id=int(turn_id) if str(turn_id).isdigit() else None,
                )
            )
        return hits

    def apply_simple_correction(
        self,
        *,
        new_value: str,
        old_value: str,
    ) -> Optional[int]:
        """
        Rewrite the newest matching raw memory in place.

        The original sentence structure is preserved so later FTS5 queries
        still match its action words, while the corrected value replaces the
        stale value.
        """
        clean_new = re.sub(
            r"\s+",
            " ",
            str(new_value).strip(),
        )
        clean_old = re.sub(
            r"\s+",
            " ",
            str(old_value).strip(),
        )

        if not clean_new or not clean_old:
            return None

        candidates = self.search_memory(
            clean_old,
            limit=5,
        )

        best_match = None

        for hit in candidates:
            span = _best_fuzzy_word_span(
                hit.raw_text,
                clean_old,
            )

            if span is None:
                continue

            start, end, score = span

            candidate = (
                score,
                hit.created_ts,
                hit.id,
                hit.raw_text,
                start,
                end,
            )

            if best_match is None or candidate[:2] > best_match[:2]:
                best_match = candidate

        if best_match is None:
            return None

        (
            score,
            _created_ts,
            memory_id,
            raw_text,
            start,
            end,
        ) = best_match

        if score < 0.60:
            return None

        corrected = (
            raw_text[:start]
            + clean_new
            + raw_text[end:]
        )
        corrected = re.sub(
            r"\s+",
            " ",
            corrected,
        ).strip()

        search_text = normalize_for_search(
            corrected,
        )

        if not search_text:
            return None

        self.conn.execute(
            """
            UPDATE memory_fts
            SET raw_text = ?,
                search_text = ?,
                created_ts = ?
            WHERE rowid = ?
            """,
            (
                corrected,
                search_text,
                time.time(),
                int(memory_id),
            ),
        )
        self.conn.commit()

        return int(memory_id)

    def count(self) -> int:
        return int(
            self.conn.execute("SELECT COUNT(*) AS c FROM memory_fts").fetchone()["c"]
        )

    def debug_dump(self) -> List[dict]:
        rows = self.conn.execute(
            "SELECT rowid, raw_text, search_text, created_ts, turn_id FROM memory_fts ORDER BY rowid"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        return {"count": self.count(), "max_memories": self.max_memories}
