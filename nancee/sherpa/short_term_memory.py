from collections import deque


class ShortTermMemory:
    def __init__(self, max_turns=3):
        self._turns = deque()

    def add_turn(
        self,
        user_text,
        assistant_text,
    ):
        self._turns.append(
            {
                "user": user_text.strip(),
                "assistant": assistant_text.strip(),
            }
        )

    def get_messages(self):
        messages = []

        for turn in self._turns:
            messages.append(
                {
                    "role": "user",
                    "content": turn["user"],
                    }
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": turn["assistant"],
                }
            )

        return messages

    def clear(self):
        self._turns.clear()
