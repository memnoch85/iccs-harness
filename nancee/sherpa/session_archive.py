from session_memory_store import SessionMemoryStore, format_memory_overlay, MemoryHit


class SessionArchive:
    """FTS5-backed raw utterance recall memory. Preserves old API shape."""

    def __init__(self, max_turns=24):
        self.max_turns = int(max_turns)
        self.store = SessionMemoryStore(max_memories=self.max_turns)
        self._next_turn_id = 1

    def add_turn(self, user_text, assistant_text='Okay.'):
        memory_id = self.store.add_memory(user_text, turn_id=self._next_turn_id)
        self._next_turn_id += 1
        return memory_id

    def apply_simple_correction(self, *, new_value, old_value):
        return self.store.apply_simple_correction(
            new_value=new_value,
            old_value=old_value,
        )

    def retrieve(self, query, limit=1, min_score=None, snippet_words=None, **kwargs):
        hits = self.store.search_memory(query, limit=limit)
        return [{
            'id': hit.id,
            'user': hit.raw_text,
            'user_text': hit.raw_text,
            'search_text': hit.search_text,
            'bm25_score': hit.bm25_score,
            'score': -hit.bm25_score,
            'created_ts': hit.created_ts,
            'turn_id': hit.turn_id,
        } for hit in hits]

    def format_related_context(self, hits, max_characters=None, *args, **kwargs):
        memory_hits = []
        for hit in hits or []:
            memory_hits.append(MemoryHit(
                id=int(hit.get('id', 0)),
                raw_text=hit.get('user') or hit.get('user_text') or '',
                search_text=hit.get('search_text', ''),
                bm25_score=float(hit.get('bm25_score', 0.0)),
                created_ts=float(hit.get('created_ts', 0.0)),
                turn_id=hit.get('turn_id'),
            ))
        return format_memory_overlay(memory_hits, max_characters=max_characters)

    def debug_snapshot(self):
        dump = self.store.debug_dump()
        return {
            'max_turns': self.max_turns,
            'turn_count': self.store.count(),
            'message_count': self.store.count(),
            'archive_characters': sum(len(row.get('raw_text') or '') for row in dump),
            'stats': self.store.get_stats(),
            'rows': dump,
        }

    def __len__(self):
        return self.store.count()

    def get_stats(self):
        return self.store.get_stats()
