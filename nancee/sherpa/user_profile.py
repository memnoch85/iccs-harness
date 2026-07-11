from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import (
    USER_PROFILE_CONTEXT_MAX_CHARACTERS,
    USER_PROFILE_FILE,
)


class UserProfile:
    def __init__(self, facts: dict[str, Any] | None = None):
        self.facts = facts or {}

    @classmethod
    def load(cls, path: str | None = None) -> "UserProfile":
        profile_path = Path(path or USER_PROFILE_FILE).expanduser()

        try:
            data = json.loads(
                profile_path.read_text(
                    encoding="utf-8",
                )
            )

        except FileNotFoundError:
            return cls({})

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            print(
                f"[USER PROFILE] Could not load {profile_path}: {error!r}",
                flush=True,
            )
            return cls({})

        if not isinstance(data, dict):
            print(
                f"[USER PROFILE] Ignoring non-object profile file: {profile_path}",
                flush=True,
            )
            return cls({})

        return cls(data)

    def is_empty(self) -> bool:
        return not bool(self.facts)

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, bool):
            return "true" if value else "false"

        if isinstance(value, (int, float)):
            return str(value)

        if isinstance(value, list):
            parts = [
                UserProfile._format_value(item)
                for item in value
            ]

            return ", ".join(
                part for part in parts
                if part
            )

        if isinstance(value, dict):
            parts = []

            for key, item in sorted(value.items()):
                formatted = UserProfile._format_value(item)

                if formatted:
                    parts.append(f"{key}: {formatted}")

            return "; ".join(parts)

        return str(value).strip()

    @staticmethod
    def _question_tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(
                r"[a-zA-Z0-9]+",
                str(text),
            )
        }

    def direct_answer(self, user_text: str) -> str:
        """
        Deterministic answers for explicit profile facts.

        This is not FTS5 recall.
        This is not regex fact extraction.
        This only answers from already-confirmed structured profile fields.
        """

        tokens = self._question_tokens(user_text)

        name = self._format_value(
            self.facts.get("name")
        )

        vehicle = self._format_value(
            self.facts.get("vehicle")
        )

        project = self._format_value(
            self.facts.get("project")
        )

        if name and (
            "name" in tokens
            or (
                "who" in tokens
                and "am" in tokens
                and "i" in tokens
            )
        ):
            return f"Your name is {name}."

        if vehicle and (
            "vehicle" in tokens
            or "car" in tokens
            or "drive" in tokens
            or "driving" in tokens
        ):
            return f"You drive a {vehicle}."

        if project and (
            "project" in tokens
            or "nancee" in tokens
        ):
            return f"Your project is {project}."

        return ""

    def format_context(
        self,
        max_characters: int | None = None,
    ) -> str:
        if not self.facts:
            return ""

        max_characters = max_characters or USER_PROFILE_CONTEXT_MAX_CHARACTERS

        lines = [
            "KNOWN USER PROFILE:",
            "These are stable facts about the human user, not about Nancee.",
            "Use them only when relevant.",
            "If the answer is not in the user profile or retrieved memory, say you do not remember.",
            "PROFILE FACTS:",
        ]

        for key, value in sorted(self.facts.items()):
            formatted = self._format_value(value)

            if not formatted:
                continue

            clean_key = str(key).replace("_", " ").strip()
            lines.append(f"- {clean_key}: {formatted}")

        text = "\n".join(lines)

        if max_characters and len(text) > max_characters:
            text = text[:max_characters].rstrip()

        return text
