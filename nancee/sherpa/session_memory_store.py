import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional, List

STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'can', 'could',
    'did', 'do', 'does', 'for', 'from', 'how', 'i', 'im', 'is', 'it',
    'me', 'my', 'of', 'on', 'or', 'please', 'that', 'the', 'this',
    'to', 'was', 'were', 'what', 'when', 'where', 'who', 'why', 'with',
    'would', 'you', 'your', 'nancy', 'nancee', 'hey', 'hello', 'hi',
    'okay', 'ok', 'so', 'well', 'just', 'remember', 'recall', 'should',
}

FILLER_ONLY = {'ok', 'okay', 'yes', 'no', 'sure', 'thanks', 'thank you', 'bye'}

@dataclass
class MemoryHit:
    id: int
    raw_text: str
    search_text: str
    bm25_score: float
    created_ts: float
    turn_id: Optional[int]


def tokenize(text: str) -> List[str]:
    text = str(text).lower().replace("'", ' ')
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return [tok for tok in text.split() if tok and tok not in STOPWORDS]


def normalize_for_search(text: str) -> str:
    # FTS5-only: no aliases, no semantic expansion.
    return ' '.join(tokenize(text))


def make_fts_query(text: str) -> str:
    tokens = tokenize(text)
    if not tokens:
        return ''
    safe = []
    seen = set()
    for tok in tokens:
        tok = re.sub(r'[^a-z0-9]', '', tok)
        if tok and tok not in seen:
            seen.add(tok)
            safe.append(tok)
    return ' OR '.join(safe)


def should_store_memory(raw_text: str) -> bool:
    raw = str(raw_text).strip()
    if not raw:
        return False
    if raw.lower() in FILLER_ONLY:
        return False
    return len(tokenize(raw)) >= 2


def format_memory_overlay(hits: List[MemoryHit], max_characters: Optional[int] = None) -> str:
    if not hits:
        return ''

    lines = [
        'RELEVANT USER MEMORY:',
        'The lines below are direct quotes from the human user, not from Nancee.',
        'Inside those quotes, I/me/my means the human user.',
        'When answering, convert quoted I/me/my into you/your.',
        'Never answer user-memory questions with I/my.',
        'Only say I/my when talking about Nancee.',
        'USER MEMORY QUOTES:',
    ]

    seen = set()
    for hit in hits:
        raw = str(hit.raw_text).strip()
        if not raw or raw.lower() in seen:
            continue
        seen.add(raw.lower())
        escaped = raw.replace('"', "'")
        lines.append(f'- Human user said: "{escaped}"')

    text = '\n'.join(lines)
    if max_characters and len(text) > max_characters:
        text = text[:max_characters].rstrip()
    return text


class SessionMemoryStore:
    def __init__(self, max_memories: int = 24, db_path: Optional[str] = None):
        self.max_memories = int(max_memories)
        self.conn = sqlite3.connect(db_path or ':memory:')
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
            (str(raw_text).strip(), search_text, now, '' if turn_id is None else str(turn_id)),
        )
        self.conn.commit()
        self._evict_old()
        return int(cur.lastrowid)

    def _evict_old(self) -> None:
        if self.max_memories <= 0:
            return
        count = int(self.conn.execute('SELECT COUNT(*) AS c FROM memory_fts').fetchone()['c'])
        if count <= self.max_memories:
            return
        extra = count - self.max_memories
        rows = self.conn.execute(
            'SELECT rowid FROM memory_fts ORDER BY created_ts ASC LIMIT ?',
            (extra,),
        ).fetchall()
        for row in rows:
            self.conn.execute('DELETE FROM memory_fts WHERE rowid = ?', (int(row['rowid']),))
        self.conn.commit()

    def search_memory(self, query: str, limit: int = 1) -> List[MemoryHit]:
        match_query = make_fts_query(query)
        if not match_query:
            return []
        rows = self.conn.execute(
            """
            SELECT rowid, raw_text, search_text, created_ts, turn_id,
                   bm25(memory_fts) AS bm25_score
            FROM memory_fts
            WHERE memory_fts MATCH ?
            ORDER BY bm25_score
            LIMIT ?
            """,
            (match_query, int(limit)),
        ).fetchall()
        hits = []
        for row in rows:
            turn_id = row['turn_id']
            hits.append(MemoryHit(
                id=int(row['rowid']),
                raw_text=row['raw_text'],
                search_text=row['search_text'],
                bm25_score=float(row['bm25_score']),
                created_ts=float(row['created_ts']),
                turn_id=int(turn_id) if str(turn_id).isdigit() else None,
            ))
        return hits

    def count(self) -> int:
        return int(self.conn.execute('SELECT COUNT(*) AS c FROM memory_fts').fetchone()['c'])

    def debug_dump(self) -> List[dict]:
        rows = self.conn.execute(
            'SELECT rowid, raw_text, search_text, created_ts, turn_id FROM memory_fts ORDER BY rowid'
        ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        return {'count': self.count(), 'max_memories': self.max_memories}
