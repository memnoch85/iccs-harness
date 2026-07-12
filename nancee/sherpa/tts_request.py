from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

EMPHASIS_PATTERN = re.compile(r"\*([^*\n]+)\*")


@dataclass(frozen=True)
class TtsRequest:
    text: str
    speed: float
    emphasized: bool = False
    first_audio_callback: Callable[[], None] | None = None
    allow_gap_filler: bool = False


def build_tts_request(
    text,
    normal_speed,
    emphasis_speed,
    first_audio_callback=None,
    allow_gap_filler=False,
):
    clean_text = text.strip()

    if not clean_text:
        return None

    emphasized = bool(EMPHASIS_PATTERN.search(clean_text))

    spoken_text = EMPHASIS_PATTERN.sub(
        r"\1",
        clean_text,
    )

    # Remove unmatched marker characters so Kokoro never
    # attempts to speak "asterisk".
    spoken_text = spoken_text.replace(
        "*",
        "",
    ).strip()

    if not spoken_text:
        return None

    speed = emphasis_speed if emphasized else normal_speed

    return TtsRequest(
        text=spoken_text,
        speed=speed,
        emphasized=emphasized,
        first_audio_callback=first_audio_callback,
        allow_gap_filler=bool(allow_gap_filler),
    )
