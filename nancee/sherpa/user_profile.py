from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import USER_PROFILE_FILE


class UserProfile:
    def __init__(
        self,
        facts: dict[str, Any] | None = None,
    ):
        self.facts = facts or {}

    @classmethod
    def load(
        cls,
        path: str | None = None,
    ) -> "UserProfile":
        profile_path = Path(
            path or USER_PROFILE_FILE
        ).expanduser()

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
                "[USER PROFILE] "
                f"Could not load {profile_path}: "
                f"{error!r}",
                flush=True,
            )

            return cls({})

        if not isinstance(data, dict):
            print(
                "[USER PROFILE] "
                "Ignoring non-object profile file: "
                f"{profile_path}",
                flush=True,
            )

            return cls({})

        return cls(data)

    def is_empty(self) -> bool:
        return not bool(self.facts)
