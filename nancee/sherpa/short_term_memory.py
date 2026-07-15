from collections import deque
from copy import deepcopy


class ShortTermMemory:
    def __init__(self, max_turns=None):
        if max_turns is not None:
            if isinstance(max_turns, bool) or not isinstance(max_turns, int):
                raise TypeError("max_turns must be a non-negative integer or None.")

            if max_turns < 0:
                raise ValueError("max_turns must be a non-negative integer or None.")

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

        # max_turns=0 means do not keep active prompt history.
        if self._max_turns == 0:
            return None

        evicted_turn = None

        if self._max_turns is not None and len(self._turns) == self._max_turns:
            evicted_turn = deepcopy(self._turns[0])

        self._turns.append({"user": clean_user_text, "assistant": clean_assistant_text})
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
