from __future__ import annotations

import sqlite3
import time

from session_memory_store import make_fts_query, normalize_for_search, tokenize


_MODEL_RECALL_NOISE = {
    "about",
    "again",
    "answer",
    "answers",
    "before",
    "earlier",
    "explain",
    "explained",
    "explanation",
    "last",
    "mention",
    "mentioned",
    "recommend",
    "recommended",
    "repeat",
    "response",
    "said",
    "say",
    "saying",
    "suggest",
    "suggested",
    "tell",
    "telling",
    "time",
    "told",
}


class AssistantSessionArchive:
    """Separate FTS5 archive for selected assistant responses.

    The visible/replayed value is only the assistant response. Search text also
    includes the user question that caused that response, which makes later
    requests such as "what did you say about prefix caching" reliable even if
    the answer itself begins with a pronoun instead of repeating the topic.
    """

    def __init__(self, max_turns: int = 384) -> None:
        self.max_turns = int(max_turns)
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self._next_turn_id = 1
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS assistant_memory_fts USING fts5(
                raw_text UNINDEXED,
                search_text,
                source_user_text UNINDEXED,
                created_ts UNINDEXED,
                turn_id UNINDEXED,
                tokenize='porter unicode61'
            )
            """
        )
        self.conn.commit()

    def add_response(
        self,
        *,
        user_text: str,
        assistant_text: str,
    ) -> int | None:
        clean_answer = " ".join(str(assistant_text).strip().split())
        clean_user = " ".join(str(user_text).strip().split())

        if not clean_answer:
            return None

        search_text = normalize_for_search(
            f"{clean_user} {clean_answer}"
        )

        if not search_text:
            return None

        cursor = self.conn.execute(
            """
            INSERT INTO assistant_memory_fts(
                raw_text,
                search_text,
                source_user_text,
                created_ts,
                turn_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                clean_answer,
                search_text,
                clean_user,
                time.time(),
                str(self._next_turn_id),
            ),
        )
        self.conn.commit()
        self._next_turn_id += 1
        self._evict_old()

        if cursor.lastrowid is None:
            raise RuntimeError(
                "Assistant memory insert completed without a row ID."
            )

        return int(cursor.lastrowid)

    def _evict_old(self) -> None:
        if self.max_turns <= 0:
            return

        count = self.count()

        if count <= self.max_turns:
            return

        extra = count - self.max_turns
        rows = self.conn.execute(
            """
            SELECT rowid
            FROM assistant_memory_fts
            ORDER BY created_ts ASC, rowid ASC
            LIMIT ?
            """,
            (extra,),
        ).fetchall()

        for row in rows:
            self.conn.execute(
                "DELETE FROM assistant_memory_fts WHERE rowid = ?",
                (int(row["rowid"]),),
            )

        self.conn.commit()

    def _topical_query(self, query: str) -> str:
        topical_tokens = [
            token
            for token in tokenize(query)
            if token not in _MODEL_RECALL_NOISE
        ]
        return " ".join(topical_tokens)

    def retrieve_response(self, query: str) -> str:
        topical_query = self._topical_query(query)

        if not topical_query:
            row = self.conn.execute(
                """
                SELECT raw_text
                FROM assistant_memory_fts
                ORDER BY created_ts DESC, rowid DESC
                LIMIT 1
                """
            ).fetchone()

            return "" if row is None else str(row["raw_text"]).strip()

        match_query = make_fts_query(topical_query)

        if not match_query:
            return ""

        row = self.conn.execute(
            """
            SELECT raw_text, bm25(assistant_memory_fts) AS bm25_score
            FROM assistant_memory_fts
            WHERE assistant_memory_fts MATCH ?
            ORDER BY bm25_score ASC, created_ts DESC, rowid DESC
            LIMIT 1
            """,
            (match_query,),
        ).fetchone()

        return "" if row is None else str(row["raw_text"]).strip()

    def close(self) -> None:
        self.conn.close()

    def count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM assistant_memory_fts"
        ).fetchone()
        return 0 if row is None else int(row["c"])

    def get_stats(self) -> dict:
        return {
            "count": self.count(),
            "max_memories": self.max_turns,
        }

    def debug_dump(self) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT rowid, raw_text, search_text, source_user_text,
                   created_ts, turn_id
            FROM assistant_memory_fts
            ORDER BY rowid
            """
        ).fetchall()
        return [dict(row) for row in rows]
