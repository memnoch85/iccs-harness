from collections import deque
from copy import deepcopy


class ShortTermMemory:
    def __init__(self, max_turns=None):
        if max_turns is not None:
            if isinstance(max_turns, bool) or not isinstance(max_turns, int):
                raise TypeError("max_turns must be a positive integer or None.")
            if max_turns <= 0:
                raise ValueError("max_turns must be a positive integer or None.")

        self._max_turns = max_turns
        self._turns = deque(maxlen=max_turns)

    @staticmethod
    def _clean_text(value):
        return str(value).strip()

    def add_turn(self, user_text, assistant_text):
        clean_user_text = self._clean_text(user_text)
        clean_assistant_text = self._clean_text(assistant_text)

        if not clean_user_text:
            raise ValueError("user_text cannot be empty.")
        if not clean_assistant_text:
            raise ValueError("assistant_text cannot be empty.")

        evicted_turn = None
        if self._max_turns is not None and len(self._turns) == self._max_turns:
            evicted_turn = deepcopy(self._turns[0])

        self._turns.append(
            {
                "user": clean_user_text,
                "assistant": clean_assistant_text,
            }
        )

        return evicted_turn

    def get_messages(self):
        messages = []
        for turn in self._turns:
            messages.append({"role": "user", "content": turn["user"]})
            messages.append({"role": "assistant", "content": turn["assistant"]})
        return messages

    def get_turns_snapshot(self):
        return deepcopy(list(self._turns))

    def get_stats(self):
        history_characters = sum(
            len(turn["user"]) + len(turn["assistant"]) for turn in self._turns
        )
        return {
            "max_turns": self._max_turns,
            "turn_count": len(self._turns),
            "message_count": len(self._turns) * 2,
            "history_characters": history_characters,
        }

    def snapshot(self):
        return {
            "max_turns": self._max_turns,
            "turns": self.get_turns_snapshot(),
        }

    def clear(self):
        self._turns.clear()

    def clear_session(self):
        self.clear()
        import json
        import re
        import sqlite3
        import time
        from dataclasses import dataclass
        from pathlib import Path
        from typing import Dict, Iterable, List, Optional

        # ====================================================================
        # CONFIGURATION - Edit this section to tune behavior
        # ====================================================================

        # Aliases loaded from JSON file if it exists, otherwise use built-in map
        ALIAS_FILE = Path(__file__).parent / "aliases.json"

        # Built-in fallback aliases (generic search terms only)
        FALLBACK_ALIASES = {
            "drive": ["car", "vehicle", "driving"],
            "drives": ["car", "vehicle", "driving"],
            "driving": ["drive", "car", "vehicle"],
            "car": ["vehicle", "drive"],
            "vehicle": ["car", "drive"],
            "truck": ["vehicle", "car"],
            "suv": ["vehicle", "car"],
            "own": ["have", "has", "owned", "item", "possess"],
            "owns": ["have", "has", "owned", "item", "possess"],
            "owned": ["own", "have", "item"],
            "have": ["own", "owned", "item"],
            "got": ["bought", "acquired", "purchased", "found", "picked"],
            "get": ["got", "bought", "acquire", "find"],
            "bought": ["got", "acquired", "purchased"],
            "buy": ["bought", "purchase", "get"],
            "purchased": ["bought", "got", "acquired"],
            "found": ["got", "acquired"],
            "store": ["market", "shop"],
            "market": ["store", "shop"],
            "shop": ["store", "market"],
            "name": ["call", "nickname", "preferred"],
            "nickname": ["name", "call", "preferred"],
            "call": ["name", "nickname", "preferred"],
            "called": ["name", "nickname", "preferred"],
            "preferred": ["name", "nickname", "call"],
            "like": ["love", "prefer", "favorite", "enjoy"],
            "likes": ["love", "prefer", "favorite", "enjoy"],
            "love": ["like", "prefer", "favorite", "enjoy"],
            "loves": ["like", "prefer", "favorite", "enjoy"],
            "prefer": ["like", "love", "favorite"],
            "favorite": ["like", "love", "prefer"],
            "enjoy": ["like", "love", "prefer"],
            "work": ["job", "career", "works", "working"],
            "live": ["lives", "living", "home", "reside", "resides"],
            "lives": ["live", "living", "home", "reside"],
            "home": ["live", "residence"],
        }

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
            "so",
            "well",
            "just",
            "remember",
            "recall",
        }

        # ====================================================================
        # ALIAS LOADER
        # ====================================================================

        def load_aliases() -> Dict[str, List[str]]:
            """Load aliases from JSON file, falling back to built-in map."""
            if ALIAS_FILE.exists():
                try:
                    with open(ALIAS_FILE, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            # Merge with fallback, but allow override
                            merged = FALLBACK_ALIASES.copy()
                            merged.update(loaded)
                            return merged
                except (json.JSONDecodeError, OSError) as e:
                    print(f"[ALIAS WARN] Could not load {ALIAS_FILE}: {e}")
            return FALLBACK_ALIASES.copy()

        ALIAS_MAP = load_aliases()

        # ====================================================================
        # CORE FUNCTIONS
        # ====================================================================

        @dataclass
        class MemoryHit:
            id: int
            raw_text: str
            search_text: str
            bm25_score: float
            access_count: int
            last_accessed_ts: float
            created_ts: float
            turn_id: Optional[int]

        def tokenize(text: str) -> List[str]:
            """Tokenize text for indexing, removing stopwords."""
            text = str(text).lower()
            text = text.replace("'", " ")
            text = re.sub(r"[^a-z0-9\s]", " ", text)
            return [tok for tok in text.split() if tok and tok not in STOPWORDS]

        def expand_tokens(tokens: Iterable[str]) -> List[str]:
            """Expand tokens with generic aliases (no topic-specific terms)."""
            expanded = []
            seen = set()
            for token in tokens:
                for item in [token] + ALIAS_MAP.get(token, []):
                    item = item.strip().lower()
                    if not item or item in STOPWORDS or item in seen:
                        continue
                    seen.add(item)
                    expanded.append(item)
            return expanded

        def normalize_for_search(text: str) -> str:
            """Convert raw text to searchable keyword string."""
            return " ".join(expand_tokens(tokenize(text)))

        def make_fts_query(text: str) -> str:
            """Convert user query to FTS5 MATCH syntax with phrase support."""
            tokens = expand_tokens(tokenize(text))
            if not tokens:
                return ""

            # Single tokens
            terms = [f'"{t}"' if " " in t else t for t in tokens if t]

            # Phrases (2-3 word sequences)
            for i in range(len(tokens) - 1):
                phrase = f"{tokens[i]} {tokens[i + 1]}"
                terms.append(f'"{phrase}"')

            # Clean tokens for safety
            clean_terms = []
            for term in terms:
                clean = re.sub(r'[^a-z0-9"\s]', "", term)
                clean = re.sub(r"\s+", " ", clean)
                clean = clean.strip()
                if clean:
                    clean_terms.append(clean)

            return " OR ".join(clean_terms)

        def should_store_memory(raw_text: str) -> bool:
            """
            Determine if text should be stored.
            Uses signal-based approach: store anything with 3+ meaningful tokens.
            """
            raw_text = str(raw_text).strip()
            if not raw_text:
                return False

            # Don't store single-word answers or empty filler
            tokens = tokenize(raw_text)
            if len(tokens) < 3:
                return False

            # Don't store pure question words
            if len(tokens) <= 2 and raw_text.lower() in {
                "ok",
                "okay",
                "yes",
                "no",
                "sure",
                "bye",
            }:
                return False

            return True

        def format_memory_overlay(
            hits: List[MemoryHit], max_characters: Optional[int] = None
        ) -> str:
            """Format retrieved memories as overlay for LLM."""
            if not hits:
                return ""

            lines = [
                "RELEVANT USER MEMORY:",
                "Perspective rule: these are memories from the human user. Answer with you/your, not I/my.",
            ]

            seen = set()
            for hit in hits:
                raw = hit.raw_text.strip()
                if not raw or raw.lower() in seen:
                    continue
                seen.add(raw.lower())
                lines.append(f"- {raw}")

            text = "\n".join(lines)
            if max_characters and len(text) > max_characters:
                text = text[:max_characters].rstrip()

            return text

        # ====================================================================
        # SESSION MEMORY STORE (FTS5 Backend)
        # ====================================================================

        class SessionMemoryStore:
            """SQLite FTS5-backed memory store with LRU eviction."""

            def __init__(self, max_memories: int = 96, db_path: Optional[str] = None):
                self.max_memories = int(max_memories)
                self.conn = sqlite3.connect(db_path or ":memory:")
                self.conn.row_factory = sqlite3.Row
                self._init_schema()

            def _init_schema(self) -> None:
                """Initialize FTS5 table and metadata tables."""
                self.conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                        raw_text UNINDEXED,
                        search_text,
                        created_ts UNINDEXED,
                        last_accessed_ts UNINDEXED,
                        access_count UNINDEXED,
                        turn_id UNINDEXED,
                        tokenize='porter unicode61'
                    )
                """)

                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory_metadata (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        raw_text TEXT,
                        created_ts REAL,
                        last_accessed_ts REAL,
                        access_count INTEGER DEFAULT 0,
                        turn_id INTEGER
                    )
                """)

                self.conn.commit()

            def _add_metadata(
                self, raw_text: str, turn_id: Optional[int] = None
            ) -> int:
                """Add metadata entry and return ID."""
                now = time.time()
                cur = self.conn.execute(
                    """INSERT INTO memory_metadata (raw_text, created_ts, last_accessed_ts, access_count, turn_id)
                       VALUES (?, ?, ?, ?, ?)""",
                    (raw_text, now, now, 0, turn_id),
                )
                self.conn.commit()
                return cur.lastrowid

            def add_memory(
                self, raw_text: str, turn_id: Optional[int] = None
            ) -> Optional[int]:
                """Add a memory to the store. Returns None if not stored."""
                if not should_store_memory(raw_text):
                    return None

                search_text = normalize_for_search(raw_text)
                if not search_text:
                    return None

                # Add metadata first
                metadata_id = self._add_metadata(raw_text, turn_id)
                now = time.time()

                # Insert into FTS5
                self.conn.execute(
                    """INSERT INTO memory_fts(rowid, raw_text, search_text, created_ts, last_accessed_ts, access_count, turn_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        metadata_id,
                        raw_text,
                        search_text,
                        now,
                        now,
                        0,
                        "" if turn_id is None else str(turn_id),
                    ),
                )
                self.conn.commit()

                self._evict_old()
                return metadata_id

            def _evict_old(self) -> None:
                """Evict oldest LAST ACCESSED memories when over limit."""
                if self.max_memories <= 0:
                    return

                # Count current rows
                row = self.conn.execute(
                    "SELECT COUNT(*) AS cnt FROM memory_fts"
                ).fetchone()
                count = int(row["cnt"])

                if count <= self.max_memories:
                    return

                # Evict rows with oldest last_accessed_ts
                to_evict = count - self.max_memories
                rows = self.conn.execute(
                    """SELECT rowid FROM memory_fts
                       ORDER BY last_accessed_ts ASC, created_ts ASC
                       LIMIT ?""",
                    (to_evict,),
                ).fetchall()

                for row in rows:
                    self.conn.execute(
                        "DELETE FROM memory_fts WHERE rowid = ?", (row["rowid"],)
                    )
                    self.conn.execute(
                        "DELETE FROM memory_metadata WHERE id = ?", (row["rowid"],)
                    )

                self.conn.commit()

            def search_memory(self, query: str, limit: int = 3) -> List[MemoryHit]:
                """Search memory using FTS5 with BM25 ranking."""
                match_query = make_fts_query(query)
                if not match_query:
                    return []

                rows = self.conn.execute(
                    """
                    SELECT rowid, raw_text, search_text, created_ts, last_accessed_ts,
                           access_count, turn_id, bm25(memory_fts) AS bm25_score
                    FROM memory_fts
                    WHERE memory_fts MATCH ?
                    ORDER BY bm25_score
                    LIMIT ?
                    """,
                    (match_query, int(limit)),
                ).fetchall()

                hits = []
                for row in rows:
                    rowid = int(row["rowid"])
                    bm25_score = float(row["bm25_score"])

                    # Update access metadata (LRU)
                    self.conn.execute(
                        """UPDATE memory_fts SET last_accessed_ts = ?, access_count = access_count + 1
                           WHERE rowid = ?""",
                        (time.time(), rowid),
                    )
                    self.conn.execute(
                        """UPDATE memory_metadata SET last_accessed_ts = ?, access_count = access_count + 1
                           WHERE id = ?""",
                        (time.time(), rowid),
                    )
                    self.conn.commit()

                    turn_id = row["turn_id"]
                    hits.append(
                        MemoryHit(
                            id=rowid,
                            raw_text=row["raw_text"],
                            search_text=row["search_text"],
                            bm25_score=bm25_score,
                            access_count=int(row["access_count"]) + 1,
                            last_accessed_ts=float(row["last_accessed_ts"]),
                            created_ts=float(row["created_ts"]),
                            turn_id=int(turn_id) if str(turn_id).isdigit() else None,
                        )
                    )

                return hits

            def count(self) -> int:
                """Return number of stored memories."""
                row = self.conn.execute(
                    "SELECT COUNT(*) AS cnt FROM memory_fts"
                ).fetchone()
                return int(row["cnt"])

            def debug_dump(self) -> List[dict]:
                """Return all memories for debugging."""
                rows = self.conn.execute(
                    """SELECT rowid, raw_text, search_text, created_ts, last_accessed_ts,
                              access_count, turn_id
                       FROM memory_fts ORDER BY rowid"""
                ).fetchall()
                return [dict(row) for row in rows]

            def get_stats(self) -> dict:
                """Return store statistics."""
                rows = self.conn.execute(
                    """SELECT COUNT(*) AS count,
                              AVG(access_count) AS avg_access,
                              MIN(created_ts) AS oldest,
                              MAX(created_ts) AS newest
                       FROM memory_fts"""
                ).fetchone()
                return {
                    "count": int(rows["count"]),
                    "avg_access": float(rows["avg_access"] or 0),
                    "oldest_ts": float(rows["oldest"] or 0),
                    "newest_ts": float(rows["newest"] or 0),
                    "max_memories": self.max_memories,
                }
