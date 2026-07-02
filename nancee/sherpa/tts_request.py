from __future__ import annotations

import re
from dataclasses import dataclass

EMPHASIS_PATTERN = re.compile(r"\*([^*\n]+)\*")


@dataclass(frozen=True)
class TtsRequest:
    text: str
    speed: float
    emphasized: bool = False


def enqueue_tts_text(text):
    request = build_tts_request(
        text=text,
        normal_speed=SPEED,
        emphasis_speed=TTS_EMPHASIS_SPEED,
    )

    if request is not None:
        text_queue.put(request)


def build_tts_request(
    text,
    normal_speed,
    emphasis_speed,
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
    )
