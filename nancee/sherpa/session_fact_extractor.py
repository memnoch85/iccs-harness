#!/usr/bin/env python3
from __future__ import annotations

import re
from typing import Any

_NAME_PATTERN = re.compile(
    r"\bmy name is\s+"
    r"([A-Za-z][A-Za-z' -]{0,40}?)"
    r"(?=\s*(?:[.!?,;]|$|\b(?:and|but|so|please)\b))",
    re.IGNORECASE,
)

_FAVORITE_BAND_PATTERN = re.compile(
    r"\bmy favorite band(?:'s name)?\s+"
    r"(?:is called|is named|is)\s+"
    r"([A-Za-z0-9][A-Za-z0-9 '&.\-]{0,60}?)"
    r"(?=\s*(?:[.!?,;]|$|\b(?:and|but|they|it)\b))",
    re.IGNORECASE,
)

_FAVORITE_MUSIC_PATTERN = re.compile(
    r"\bmy favorite (?:type|kind|genre) of music is\s+"
    r"(.{1,100}?)"
    r"(?=\s*(?:[.!?;]|$))",
    re.IGNORECASE,
)

_PRONOUN_BAND_ORIGIN_PATTERN = re.compile(
    r"\b(?:they|the band|it)\s+(?:are|is)\s+from\s+"
    r"([A-Za-z][A-Za-z0-9 ,.'\-]{1,80}?)"
    r"(?=\s*(?:[.!?;]|$))",
    re.IGNORECASE,
)

_VEHICLE_PATTERN = re.compile(
    r"(?:\bmy\s+|\bi\s+(?:have|own|drive)\s+(?:a|an)\s+)"
    r"((?:19|20)\d{2}\s+"
    r"[A-Za-z][A-Za-z0-9'\-]*"
    r"(?:\s+(?!(?:gets?|has|with|that|which|for|on|is)\b)"
    r"[A-Za-z][A-Za-z0-9'\-]*){1,3})"
    r"(?=\s*(?:[.!?,;]|$|\b(?:gets?|has|with|that|which|for|on|is)\b))",
    re.IGNORECASE,
)

_DTC_PATTERN = re.compile(
    r"\b[PCBU]\d{4}\b",
    re.IGNORECASE,
)


def _clean_fact_value(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip(" \t\r\n,.;:!?")


def _title_name(value: str) -> str:
    words = []

    for word in _clean_fact_value(value).split():
        if "'" in word:
            pieces = word.split("'")
            words.append(
                "'".join(
                    piece.capitalize()
                    for piece in pieces
                )
            )
        else:
            words.append(word.capitalize())

    return " ".join(words)


def _existing_working_state(memory: Any) -> dict[str, Any]:
    snapshot = memory.snapshot()
    working_state = snapshot.get(
        "working_state",
        {},
    )

    if not isinstance(working_state, dict):
        return {}

    return working_state


def _named_band_origin(
    user_text: str,
    favorite_band: str,
) -> str | None:
    if not favorite_band:
        return None

    pattern = re.compile(
        rf"\b{re.escape(favorite_band)}\s+"
        r"(?:is|are)\s+"
        r"(?:(?:an?\s+)?(?:American\s+)?"
        r"(?:(?:rock|punk|post-hardcore|emo)\s+)?"
        r"band\s+)?"
        r"from\s+"
        r"([A-Za-z][A-Za-z0-9 ,.'\-]{1,80}?)"
        r"(?=\s*(?:[.!?;]|$))",
        re.IGNORECASE,
    )

    match = pattern.search(user_text)

    if not match:
        return None

    return _clean_fact_value(match.group(1))


def promote_archived_facts(
    memory: Any,
    archived_turns: list[dict[str, str]],
) -> dict[str, Any]:
    """Promote deterministic user facts from archived turns.

    Only archived user text is examined. Assistant text is never trusted as
    a source of session facts. Turns are processed in chronological order, so
    a later user correction replaces an earlier value.
    """

    changes: dict[str, Any] = {}
    working_state = _existing_working_state(memory)

    session_facts = working_state.get(
        "session_facts",
        {},
    )

    if not isinstance(session_facts, dict):
        session_facts = {}

    favorite_band = str(
        session_facts.get(
            "favorite_band",
            "",
        )
    ).strip()

    existing_codes = working_state.get(
        "last_dtc_codes",
        [],
    )

    if not isinstance(existing_codes, list):
        existing_codes = []

    known_codes = [
        str(code).upper()
        for code in existing_codes
    ]
    seen_codes = set(known_codes)

    for turn in archived_turns:
        if not isinstance(turn, dict):
            continue

        user_text = str(
            turn.get(
                "user",
                "",
            )
        ).strip()

        if not user_text:
            continue

        name_match = _NAME_PATTERN.search(user_text)

        if name_match:
            user_name = _title_name(
                name_match.group(1)
            )
            memory.set_session_fact(
                "user_name",
                user_name,
            )
            changes["user_name"] = user_name

        music_match = _FAVORITE_MUSIC_PATTERN.search(
            user_text
        )

        if music_match:
            favorite_music = _clean_fact_value(
                music_match.group(1)
            )
            memory.set_session_fact(
                "favorite_music",
                favorite_music,
            )
            changes["favorite_music"] = favorite_music

        band_match = _FAVORITE_BAND_PATTERN.search(
            user_text
        )

        if band_match:
            new_favorite_band = _clean_fact_value(
                band_match.group(1)
            )

            if (
                favorite_band
                and new_favorite_band.lower()
                != favorite_band.lower()
            ):
                memory.remove_session_fact(
                    "favorite_band_origin"
                )

            favorite_band = new_favorite_band
            memory.set_session_fact(
                "favorite_band",
                favorite_band,
            )
            changes["favorite_band"] = favorite_band

        origin_match = _PRONOUN_BAND_ORIGIN_PATTERN.search(
            user_text
        )

        origin = None

        if origin_match and favorite_band:
            origin = _clean_fact_value(
                origin_match.group(1)
            )
        elif favorite_band:
            origin = _named_band_origin(
                user_text,
                favorite_band,
            )

        if origin:
            memory.set_session_fact(
                "favorite_band_origin",
                origin,
            )
            changes["favorite_band_origin"] = origin

        vehicle_match = _VEHICLE_PATTERN.search(
            user_text
        )

        if vehicle_match:
            vehicle = _clean_fact_value(
                vehicle_match.group(1)
            )
            memory.set_session_fact(
                "vehicle",
                vehicle,
            )
            changes["vehicle"] = vehicle

        for code in _DTC_PATTERN.findall(user_text):
            normalized_code = code.upper()

            if normalized_code in seen_codes:
                continue

            seen_codes.add(normalized_code)
            known_codes.append(normalized_code)

    if known_codes:
        memory.set_last_dtc_codes(
            known_codes
        )
        changes["last_dtc_codes"] = known_codes

    return changes
