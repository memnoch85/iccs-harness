from __future__ import annotations

import re
from dataclasses import dataclass

from memory_policy import (
    extract_simple_fact_correction,
    extract_storable_memory_text,
)
from recall_policy import looks_like_perspective_correction
from router_mon import RouterMonResult, classify_router_mon


@dataclass(frozen=True)
class InputRoute:
    kind: str
    normalized_text: str
    reason: str = ""
    retrieve_recall: bool = False
    explicit_recall: bool = False
    allow_weak_match: bool = False
    store_recall: bool = False
    recall_storage_text: str | None = None
    force_keep_history: bool = False
    correction: tuple[str, str] | None = None
    skip_latency_bridge: bool = False
    pending_memory_topic: str | None = None


# These are deliberately narrow deterministic routes. They are cheaper and
# more certain than statistical classification for exact conversational forms.
_FAST_AFFIRMATIVE = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "okay",
    "ok",
    "sure",
    "correct",
    "exactly",
    "absolutely",
    "definitely",
    "go ahead",
    "sounds good",
    "got it",
    "cool",
}
_FAST_NEGATIVE = {
    "no",
    "nope",
    "nah",
    "never mind",
    "nevermind",
    "absolutely not",
    "not really",
}
_FAST_FAREWELL = {
    "bye",
    "goodbye",
    "see you",
    "see ya",
    "see you later",
    "talk to you later",
    "talk later",
    "later",
    "ttyl",
    "good night",
    "gotta go",
    "got to run",
}

_QUESTION_PREFIXES = (
    "what ",
    "who ",
    "where ",
    "when ",
    "why ",
    "how ",
    "do ",
    "does ",
    "did ",
    "can ",
    "could ",
    "would ",
    "should ",
    "is ",
    "are ",
    "am ",
    "was ",
    "were ",
)

# Short hello/hi is an intentional hard UX route. It accepts zero, one, or
# two words after hello/hi so Whisper can mangle an assistant name without
# turning a tiny greeting into a classifier decision.
_HARD_GREETING_PATTERN = re.compile(
    r"^\s*(?:hello|hi)\b"
    r"(?:\s*,?\s*[^\W_]+(?:['-][^\W_]+)*){0,2}"
    r"\s*[,.!?]*\s*\Z",
    flags=re.IGNORECASE,
)

# This is only classifier-input cleanup. It does not itself choose a route.
# Assistant names are intentionally absent: routerMon is not trained around a
# fixed name and a renamed assistant should simply treat the name as extra text.
_LEADING_CONVERSATIONAL_PREFACE = re.compile(
    r"^(?:good morning|good afternoon|good evening|"
    r"hello|hi|hey|so|well|okay|ok|and|yeah|yep|yup|uh|um|hmm|"
    r"man|dude|bruh)\b[\s,!.:;\-]*",
    flags=re.IGNORECASE,
)

_AFFIRMATIVE_ANSWER_PATTERN = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|sure did|i did|i sure did|absolutely|"
    r"correct|that's right|that is right|i have|i am|i can)[.! ]*$",
    flags=re.IGNORECASE,
)

_NEGATIVE_ANSWER_PATTERN = re.compile(
    r"^(?:no|nope|not yet|i did not|i didn't|i have not|i haven't|"
    r"i am not|i'm not|i cannot|i can't)[.! ]*$",
    flags=re.IGNORECASE,
)

_PREVIOUS_QUESTION_PATTERNS = (
    (
        re.compile(r"^did\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE),
        "I did",
        "I did not",
    ),
    (
        re.compile(r"^have\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE),
        "I have",
        "I have not",
    ),
    (
        re.compile(r"^are\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE),
        "I am",
        "I am not",
    ),
    (
        re.compile(r"^were\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE),
        "I was",
        "I was not",
    ),
    (
        re.compile(r"^do\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE),
        "I",
        "I do not",
    ),
    (
        re.compile(r"^can\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE),
        "I can",
        "I cannot",
    ),
)

_ASK_ME_TOPIC_PATTERN = re.compile(
    r"^\s*(?:(?:hey|hello|hi)\b[\s,!.:;\-]*)?"
    r"(?:[A-Za-z][A-Za-z'-]{0,39}\s*,\s*)?"
    r"(?:"
    r"i\s+want\s+you\s+to\s+|"
    r"(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
    r")?"
    r"ask\s+me\s+(?P<topic>.+?)\s*[.!?]*\s*\Z",
    flags=re.IGNORECASE,
)


_EXPLICIT_MEMORY_STORE_PATTERN = re.compile(
    r"^(?:(?:hey\s+)?[A-Za-z][A-Za-z'-]{0,39}\s*,\s*)?"
    r"(?:please\s+)?(?:"
    r"remember\s+this(?:\s*:)?|"
    r"remember(?:\s+that)?|"
    r"save(?:\s+this)?(?:\s+in\s+memory)?(?:\s+that)?|"
    r"store(?:\s+this)?(?:\s+for\s+later)?(?:\s+that)?|"
    r"make\s+a\s+note(?:\s+of)?(?:\s+that)?|"
    r"keep\s+this\s+in\s+memory|"
    r"don't\s+forget(?:\s+that)?|"
    r"do\s+not\s+forget(?:\s+that)?"
    r")\s+(?P<statement>.+?)\s*$",
    flags=re.IGNORECASE,
)


def normalize_user_text(user_text: str) -> str:
    lowered = re.sub(r"\s+", " ", str(user_text).strip().lower())

    # Preserve the existing Nancee/Whisper cleanup for this implementation.
    # It is runtime normalization, not routerMon training, so the classifier is
    # still name-neutral and can be used by a differently named assistant.
    return re.sub(r"^(?:nancy|nancee|and\s+see)[,\s]+", "", lowered)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", str(text)))


def _classification_text(user_text: str) -> str:
    remaining = normalize_user_text(user_text)
    removed_preface = False

    while remaining:
        match = _LEADING_CONVERSATIONAL_PREFACE.match(remaining)

        if match is None:
            break

        removed_preface = True
        remaining = remaining[match.end():].lstrip()

    # A comma-delimited token immediately after a conversational preface is a
    # likely vocative ("Hey Becca, ..."). Strip it without knowing or training
    # the assistant's configured name.
    if removed_preface:
        remaining = re.sub(
            r"^[A-Za-z][A-Za-z'-]{0,39}\s*,\s*",
            "",
            remaining,
            count=1,
        )

    return remaining or normalize_user_text(user_text)


def _fast_normalized_text(text: str) -> str:
    cleaned = normalize_user_text(text)
    cleaned = re.sub(r"[^a-z0-9']+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _looks_question_shaped(text: str) -> bool:
    lowered = normalize_user_text(text)
    return "?" in lowered or lowered.startswith(_QUESTION_PREFIXES)


def _extract_ask_me_topic(user_text: str) -> str | None:
    candidate = re.sub(
        r"\s+",
        " ",
        str(user_text).strip(),
    )
    match = _ASK_ME_TOPIC_PATTERN.fullmatch(candidate)

    if match is None:
        return None

    topic = match.group("topic").strip().rstrip(".!?").strip()
    return topic or None


def _extract_explicit_memory_store(user_text: str) -> str | None:
    candidate = re.sub(
        r"\s+",
        " ",
        str(user_text).strip(),
    )
    match = _EXPLICIT_MEMORY_STORE_PATTERN.fullmatch(candidate)

    if match is None:
        return None

    statement = match.group("statement").strip()

    if (
        not statement
        or statement.endswith("?")
        or _word_count(statement) < 3
    ):
        return None

    return statement


def _resolve_contextual_memory(
    user_text: str,
    previous_turn: dict[str, str] | None,
) -> str | None:
    if not previous_turn:
        return None

    answer = re.sub(r"\s+", " ", str(user_text).strip())
    previous_question = re.sub(
        r"\s+",
        " ",
        str(previous_turn.get("assistant", "")).strip(),
    )

    if not previous_question.endswith("?"):
        return None

    if _AFFIRMATIVE_ANSWER_PATTERN.fullmatch(answer):
        positive = True
    elif _NEGATIVE_ANSWER_PATTERN.fullmatch(answer):
        positive = False
    else:
        return None

    for pattern, positive_prefix, negative_prefix in _PREVIOUS_QUESTION_PATTERNS:
        match = pattern.fullmatch(previous_question)

        if match is None:
            continue

        predicate = match.group("predicate").strip().rstrip(".?!")
        predicate = re.sub(r"\byour\b", "my", predicate, flags=re.IGNORECASE)

        prefix = positive_prefix if positive else negative_prefix
        resolved = re.sub(r"\s+", " ", f"{prefix} {predicate}").strip()

        return resolved[0].upper() + resolved[1:] + "."

    return None


def _reason(result: RouterMonResult) -> str:
    return f"{result.source}:{result.intent}:{result.confidence:.3f}"


def _route_from_router_mon(
    raw_text: str,
    lowered: str,
    result: RouterMonResult,
) -> InputRoute:
    intent = result.intent
    reason = _reason(result)

    if intent == "recall":
        return InputRoute(
            "recall",
            lowered,
            reason=reason,
            retrieve_recall=True,
            explicit_recall=True,
            allow_weak_match=True,
        )

    if intent == "model_recall":
        return InputRoute(
            "model_recall",
            lowered,
            reason=reason,
        )

    if intent == "memory_store":
        storage_text = (
            _extract_explicit_memory_store(raw_text)
            or extract_storable_memory_text(raw_text)
            or raw_text
        )

        return InputRoute(
            "memory_store",
            lowered,
            reason=reason,
            store_recall=True,
            recall_storage_text=storage_text,
        )

    if intent == "question":
        storable_memory_text = extract_storable_memory_text(raw_text)

        # Preserve the existing background-enrichment behavior for ordinary
        # questions. It uses the already-existing retrieved_context field; no
        # router metadata is added to the prompt.
        return InputRoute(
            "question",
            lowered,
            reason=reason,
            retrieve_recall=True,
            store_recall=storable_memory_text is not None,
            recall_storage_text=storable_memory_text,
        )

    if intent == "detailed":
        storable_memory_text = extract_storable_memory_text(raw_text)

        return InputRoute(
            "detailed",
            lowered,
            reason=reason,
            retrieve_recall=_looks_question_shaped(raw_text),
            store_recall=storable_memory_text is not None,
            recall_storage_text=storable_memory_text,
        )

    if intent == "directive":
        return InputRoute(
            "directive",
            lowered,
            reason=reason,
            pending_memory_topic=_extract_ask_me_topic(raw_text),
        )

    if intent == "clarify":
        return InputRoute(
            "clarify",
            lowered,
            reason=reason,
            force_keep_history=True,
        )

    if intent == "greeting":
        return InputRoute("greeting", lowered, reason=reason)

    if intent in {"affirmative", "negative", "farewell"}:
        return InputRoute(intent, lowered, reason=reason)

    storable_memory_text = extract_storable_memory_text(raw_text)

    return InputRoute(
        "normal",
        lowered,
        reason=reason,
        store_recall=storable_memory_text is not None,
        recall_storage_text=storable_memory_text,
    )


def route_user_input(
    user_text: str,
    *,
    previous_turn: dict[str, str] | None = None,
) -> InputRoute:
    raw_text = str(user_text).strip()
    lowered = normalize_user_text(raw_text)

    # Begin:: Checking invalid input
    if not raw_text:
        return InputRoute("invalid", lowered, reason="empty")

    if len(raw_text) > 1000:
        return InputRoute("invalid", lowered, reason="too_long")

    if not any(character.isalnum() for character in raw_text):
        return InputRoute("invalid", lowered, reason="punctuation_only")
    # End:: Checking invalid input

    # Begin:: Checking exit commands
    if lowered in {"q", "quit", "exit"}:
        return InputRoute("exit", lowered, reason="exit_command")
    # End:: Checking exit commands

    # Begin:: Checking short hello/hi greeting
    if _HARD_GREETING_PATTERN.fullmatch(raw_text):
        return InputRoute(
            "greeting",
            lowered,
            reason="leading_hello_or_hi",
            skip_latency_bridge=True,
        )
    # End:: Checking short hello/hi greeting

    # Begin:: Checking direct memory correction
    correction = extract_simple_fact_correction(raw_text)

    if correction is not None:
        return InputRoute(
            "correction",
            lowered,
            reason="simple_fact_correction",
            retrieve_recall=True,
            explicit_recall=True,
            allow_weak_match=True,
            force_keep_history=True,
            correction=correction,
        )
    # End:: Checking direct memory correction

    # Begin:: Checking perspective correction
    if looks_like_perspective_correction(lowered):
        return InputRoute(
            "perspective_correction",
            lowered,
            reason="perspective_correction",
            retrieve_recall=True,
            explicit_recall=True,
            allow_weak_match=True,
            force_keep_history=True,
        )
    # End:: Checking perspective correction

    # Begin:: Checking explicit memory storage command
    explicit_memory_store = _extract_explicit_memory_store(raw_text)

    if explicit_memory_store is not None:
        return InputRoute(
            "memory_store",
            lowered,
            reason="explicit_memory_store",
            store_recall=True,
            recall_storage_text=explicit_memory_store,
        )
    # End:: Checking explicit memory storage command

    # Begin:: Checking answer to previous assistant question
    contextual_memory = _resolve_contextual_memory(raw_text, previous_turn)

    if contextual_memory is not None:
        return InputRoute(
            "clarify",
            lowered,
            reason="contextual_answer",
            store_recall=True,
            recall_storage_text=contextual_memory,
            force_keep_history=True,
        )
    # End:: Checking answer to previous assistant question

    # Begin:: Checking obvious fast conversational routes
    fast_text = _fast_normalized_text(raw_text)

    if fast_text in _FAST_AFFIRMATIVE:
        return InputRoute("affirmative", lowered, reason="fast_affirmative")

    if fast_text in _FAST_NEGATIVE:
        return InputRoute("negative", lowered, reason="fast_negative")

    if fast_text in _FAST_FAREWELL:
        return InputRoute("farewell", lowered, reason="fast_farewell")
    # End:: Checking obvious fast conversational routes

    # Begin:: routerMon semantic routing
    classification_text = _classification_text(raw_text)
    result = classify_router_mon(classification_text)

    return _route_from_router_mon(
        raw_text,
        lowered,
        result,
    )
    # End:: routerMon semantic routing
