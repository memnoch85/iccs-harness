from __future__ import annotations

import re
from dataclasses import dataclass


_NAME_PATTERN = r"[A-Za-z][A-Za-z'\-]{1,39}"

_DIRECT_SELF_INTRO_PATTERNS = (
    re.compile(
        rf"\b(?:this is|my name is)\s+(?P<name>{_NAME_PATTERN})\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"(?:^|[.!?]\s+)(?:hi|hello|hey)?[\s,]*(?:i am|i'm)\s+"
        rf"(?P<name>{_NAME_PATTERN})\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"(?:^|[.!?]\s+)(?P<name>{_NAME_PATTERN})\s+here\b",
        flags=re.IGNORECASE,
    ),
)

_HANDOFF_INTENT = re.compile(
    r"\b(?:hand|pass|give)(?:ing)?\b.{0,120}"
    r"\b(?:headset|phone|microphone|mic)\b",
    flags=re.IGNORECASE,
)

_HANDOFF_DIRECT_NAME = re.compile(
    rf"\b(?:to|over to)\s+(?:(?:my|the)\s+[A-Za-z'\-]+\s+)?"
    rf"(?P<name>{_NAME_PATTERN})\b",
    flags=re.IGNORECASE,
)

_HANDOFF_RELATION_NAME = re.compile(
    rf"\b(?:his|her|their)\s+name\s+is\s+(?P<name>{_NAME_PATTERN})\b",
    flags=re.IGNORECASE,
)

_RETURN_TO_PRIMARY = re.compile(
    r"^(?:(?:okay|ok|alright|all right|so|hey)[, ]+)*"
    r"(?:hi[, ]+)?(?:i'm|i am)\s+back\b|"
    r"^(?:(?:okay|ok|alright|all right|so|hey)[, ]+)*"
    r"(?:it's|it is)\s+me\s+again\b|"
    r"^(?:(?:okay|ok|alright|all right|so|hey)[, ]+)*"
    r"back\s+to\s+me\b",
    flags=re.IGNORECASE,
)

_CURRENT_SPEAKER_QUERY_PATTERNS = (
    re.compile(
        r"\bwho(?:'s| is)\s+(?:currently\s+)?(?:talking|speaking)"
        r"(?:\s+(?:to|with)\s+you)?(?:\s+right\s+now)?\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bwho\s+(?:are|were)\s+you\s+(?:talking|speaking)"
        r"\s+(?:to|with)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bwho\s+you\s+(?:are|were)\s+(?:talking|speaking)"
        r"\s+(?:to|with)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bwho\s+is\s+the\s+(?:current|active)\s+speaker\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bwho\s+am\s+i\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:do|can)\s+you\s+"
        r"(?:know|remember|recall|tell\s+me)\s+who\s+i\s+am\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat(?:'s| is)\s+my\s+name\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:do|can)\s+you\s+"
        r"(?:know|remember|recall)\s+my\s+name\b",
        flags=re.IGNORECASE,
    ),
)

_NON_NAME_WORDS = {
    "back",
    "fine",
    "good",
    "great",
    "gonna",
    "going",
    "happy",
    "here",
    "old",
    "okay",
    "ready",
    "sure",
    "tired",
    "well",
}


@dataclass(frozen=True)
class SpeakerUpdate:
    action: str
    name: str | None = None
    changed: bool = False


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None

    clean = re.sub(r"\s+", " ", str(value).strip(" ,.!?\"'"))

    if not clean:
        return None

    if clean.lower() in _NON_NAME_WORDS:
        return None

    return clean[0].upper() + clean[1:]


def extract_direct_speaker_name(text: str) -> str | None:
    raw = re.sub(r"\s+", " ", str(text).strip())

    for pattern in _DIRECT_SELF_INTRO_PATTERNS:
        match = pattern.search(raw)

        if match is None:
            continue

        raw_name = match.group("name")

        # Whisper normally capitalizes proper names. Requiring that signal
        # prevents ordinary statements such as "I'm handing..." or
        # "I'm going..." from being mistaken for introductions.
        if not raw_name or not raw_name[0].isupper():
            continue

        name = _clean_name(raw_name)

        if name is not None:
            return name

    return None


def extract_handoff_speaker_name(text: str) -> str | None:
    raw = re.sub(r"\s+", " ", str(text).strip())

    if _HANDOFF_INTENT.search(raw) is None:
        return None

    relation_match = _HANDOFF_RELATION_NAME.search(raw)

    if relation_match is not None:
        return _clean_name(relation_match.group("name"))

    direct_match = _HANDOFF_DIRECT_NAME.search(raw)

    if direct_match is not None:
        return _clean_name(direct_match.group("name"))

    return None


def looks_like_primary_return(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text).strip())
    return _RETURN_TO_PRIMARY.search(normalized) is not None


def looks_like_current_speaker_query(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text).strip())

    return any(
        pattern.search(normalized)
        for pattern in _CURRENT_SPEAKER_QUERY_PATTERNS
    )


def direct_speaker_return_response() -> str:
    """Acknowledge a claimed return without asserting biometric identity."""
    return "Welcome back."


def direct_speaker_identity_response(
    current_name: str | None,
) -> str:
    """Answer from explicit session state without asking the LLM to infer identity."""
    name = _clean_name(current_name)

    if name is None:
        return "I don't know."

    return f"{name}."


class SpeakerState:
    """Small session state for the human currently using the microphone."""

    def __init__(self, primary_name: str | None = None) -> None:
        self.primary_name = _clean_name(primary_name)
        self.current_name = self.primary_name
        self.pending_name: str | None = None

    def begin_turn(self) -> SpeakerUpdate:
        if self.pending_name is None:
            return SpeakerUpdate("unchanged", self.current_name, False)

        next_name = self.pending_name
        self.pending_name = None
        changed = next_name != self.current_name
        self.current_name = next_name

        return SpeakerUpdate("handoff_activated", next_name, changed)

    def observe(self, text: str) -> SpeakerUpdate:
        raw = re.sub(r"\s+", " ", str(text).strip())

        if self.primary_name and _RETURN_TO_PRIMARY.search(raw):
            changed = self.current_name != self.primary_name
            self.current_name = self.primary_name
            self.pending_name = None
            return SpeakerUpdate("primary_returned", self.current_name, changed)

        direct_name = extract_direct_speaker_name(raw)

        if direct_name is not None:
            changed = direct_name != self.current_name
            self.current_name = direct_name
            self.pending_name = None
            return SpeakerUpdate("identified", direct_name, changed)

        handoff_name = extract_handoff_speaker_name(raw)

        if handoff_name is not None:
            changed = handoff_name != self.pending_name
            self.pending_name = handoff_name
            return SpeakerUpdate("handoff_pending", handoff_name, changed)

        return SpeakerUpdate("unchanged", self.current_name, False)

    def prompt_context_for(self, name: str | None) -> str:
        clean_name = _clean_name(name)

        if clean_name is None or clean_name == self.primary_name:
            return ""

        return (
            f"ACTIVE SPEAKER: {clean_name}. "
            f"Address this person as {clean_name} when natural. "
            "This is temporary session state; do not replace the primary "
            "user's stored identity."
        )

    def prompt_context(self) -> str:
        return self.prompt_context_for(self.current_name)

    def next_prompt_context(self) -> str:
        return self.prompt_context_for(
            self.pending_name or self.current_name
        )
