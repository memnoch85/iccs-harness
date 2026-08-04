from __future__ import annotations

import re
from dataclasses import dataclass

from memory_policy import (
    extract_simple_fact_correction,
    extract_storable_memory_text,
    is_complete_memory_statement,
    looks_like_personal_fact_fragment,
    looks_like_personal_fact_question,
)
from recall_policy import looks_like_perspective_correction


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

_RECALL_QUERY_PATTERNS = (
    r"\bdo you remember\b",
    r"\bcan you remember\b",
    r"\bdo you recall\b",
    r"\bcan you recall\b",
    r"\btell me what my\b",
    r"\bcan you tell me what my\b",
    r"\bwhat did i\b",
    r"\bwhere did i\b",
    r"\bwhere do i\b",
    r"\bwhere am i\b",
    r"\bwhat do i\b",
    r"\bwhat is my\b",
    r"\bwhat's my\b",
    r"\bwho is my\b",
    r"\bwho's my\b",
    r"\bwhere is my\b",
    r"\bwhere are my\b",
    r"\bwhere is our\b",
    r"\bwhere are our\b",
    r"\bwhere does my\b",
    r"\bwhere do my\b",
    r"\bwhere does our\b",
    r"\bwhere do our\b",
    r"\bwhat .* did i mention\b",
    r"\bwhat .* did i tell you\b",
    r"\bi told you .* earlier\b",
)


#pattern to match greetings Hi, hello  + up to 2 words, incase whisper botches the name.
_HARD_GREETING_PATTERN = re.compile(
    r"^\s*(?:hello|hi)\b"
    r"(?:\s*,?\s*[^\W_]+(?:['-][^\W_]+)*){0,2}"
    r"\s*[,.!?]*\s*\Z",
    flags=re.IGNORECASE,
)

_LEADING_GREETING_TOKEN = re.compile(
    r"^(?:good morning|good afternoon|good evening|"
    r"hello|hi|hey|nancee|nancy|nance|"
    r"so|well|okay|ok|and|yeah|yep|yup|uh|um|hmm|"
    r"man|dude|bruh)\b[\s,!.:;\-]*",
    flags=re.IGNORECASE,
)

_GREETING_CHECKIN_PATTERN = re.compile(
    r"^(?:"
    r"how are you(?: doing)?(?: today)?|"
    r"how(?:['’]?s| is) it going(?: today)?|"
    r"how(?:['’]?s| is) your "
    r"(?:day|evening|eveing|night|morning)(?: going)?|"
    r"how was your (?:day|evening|eveing|night|morning)|"
    r"what(?:['’]?s| is) up|"
    r"you there"
    r")[?!. ]*$",
    flags=re.IGNORECASE,
)

_BACKCHANNEL_PATTERN = re.compile(
    r"^(?:okay|ok|alright|right|sure|thanks|thank you|sounds good|got it|cool)"
    r"[.! ]*$",
    flags=re.IGNORECASE,
)

_DETAILED_PATTERN = re.compile(
    r"\b(?:"
    r"explain|explaining|walk me through|step by step|in detail|detailed|"
    r"deep dive|why does|why do|why is|how does|how do|compare|"
    r"difference between|what causes|diagnose|troubleshoot|"
    r"reason through|break down|relationship to|relationship between"
    r")\b",
    flags=re.IGNORECASE,
)

_EXACT_SENTENCE_COUNT_PATTERN = re.compile(
    r"\bexactly\s+"
    r"(?:one|two|three|four|five|\d+)\s+"
    r"(?:complete\s+)?sentences?\b",
    flags=re.IGNORECASE,
)

_MULTI_PART_QUESTION_PATTERN = re.compile(
    r"^(?:who|what|where|when|why|how)\b"
    r".+\band\s+(?:who|what|where|when|why|how)\b",
    flags=re.IGNORECASE,
)

_COMMAND_PATTERN = re.compile(
    r"^(?:ask(?: me)?|tell me|show me|give me|help me|ask|please|can you|could you|would you|"
    r"remind me|name|set|start|stop|open|close|play|pause|call|send|"
    r"i want you to|i need you to|i would like you to|i'd like you to)\b",
    flags=re.IGNORECASE,
)

_DIRECTED_REQUEST_PATTERN = re.compile(
    r"\b(?:you|nancee|nancy)\s+to\s+[a-z][a-z'\-]*\b",
    flags=re.IGNORECASE,
)

_PERSONAL_UPDATE_START_PATTERN = re.compile(
    r"^(?:i\b|i'm\b|i’ve\b|i've\b|i just\b|my\b|we\b|we're\b|we've\b|"
    r"today\b|yesterday\b|this morning\b|this afternoon\b|tonight\b)",
    flags=re.IGNORECASE,
)

_IMPLIED_I_ACTION_PATTERN = re.compile(
    r"^(?:bought|purchased|got|finished|completed|wired|installed|built|"
    r"made|found|lost|parked|left|put|ordered|ate|drank|went|met|saw|"
    r"called|received|returned|submitted|applied)\b",
    flags=re.IGNORECASE,
)

_DECLARATIVE_VERB_PATTERN = re.compile(
    r"\b(?:"
    r"am|is|are|was|were|has|have|had|own|owns|drive|drives|like|likes|"
    r"love|loves|hate|hates|prefer|prefers|use|uses|work|works|live|lives|"
    r"need|want|bought|buy|got|went|saw|finished|started|made|found|ordered|"
    r"picked|feel|felt|think|believe|plan|submitted|applied|installed|built|"
    r"lost|won|called|met|watched|ate|drank|parked|winding|sucked|hurt|"
    r"arrived|left|returned|received|completed|wired"
    r")\b",
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
    (re.compile(r"^did\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE), "I did", "I did not"),
    (re.compile(r"^have\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE), "I have", "I have not"),
    (re.compile(r"^are\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE), "I am", "I am not"),
    (re.compile(r"^were\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE), "I was", "I was not"),
    (re.compile(r"^do\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE), "I", "I do not"),
    (re.compile(r"^can\s+you\s+(?P<predicate>.+)\?$", re.IGNORECASE), "I can", "I cannot"),
)


def normalize_user_text(user_text: str) -> str:
    lowered = re.sub(r"\s+", " ", str(user_text).strip().lower())
    return re.sub(r"^(?:nancy|nancee|and\s+see)[,\s]+", "", lowered)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", str(text)))


def _strip_leading_greeting_preface(text: str) -> tuple[str, bool]:
    remaining = re.sub(r"\s+", " ", str(text).strip())
    removed = False

    while remaining:
        match = _LEADING_GREETING_TOKEN.match(remaining)

        if match is None:
            break

        removed = True
        remaining = remaining[match.end():].lstrip()

    return remaining, removed


def _classification_text(user_text: str) -> str:
    substantive, _ = _strip_leading_greeting_preface(user_text)
    return substantive or re.sub(r"\s+", " ", str(user_text).strip())


_EXPLICIT_MEMORY_STORE_PATTERN = re.compile(
    r"^(?:please\s+)?(?:"
    r"remember\s+this(?:\s*:)?|"
    r"remember(?:\s+that)?|"
    r"don't\s+forget(?:\s+that)?|"
    r"do\s+not\s+forget(?:\s+that)?"
    r")\s+(?P<statement>.+?)\s*$",
    flags=re.IGNORECASE,
)


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


def route_user_input(
    user_text: str,
    *,
    previous_turn: dict[str, str] | None = None,
) -> InputRoute:
    raw_text = str(user_text).strip()
    lowered = normalize_user_text(raw_text)
    classification_text = _classification_text(lowered)
    word_total = _word_count(classification_text)
    correction = extract_simple_fact_correction(raw_text)
    complete_statement = is_complete_memory_statement(raw_text)
    storable_memory_text = extract_storable_memory_text(raw_text)
    personal_fact_fragment = looks_like_personal_fact_fragment(raw_text)
    contextual_memory = _resolve_contextual_memory(raw_text, previous_turn)
    question_like = "?" in lowered or lowered.startswith(_QUESTION_PREFIXES)
    explicit_memory_store = _extract_explicit_memory_store(raw_text)
    hard_greeting = bool(
        _HARD_GREETING_PATTERN.match(raw_text)
    )

    greeting_substantive, had_greeting_preface = (
        _strip_leading_greeting_preface(raw_text)
    )

    greeting_match = bool(
        _BACKCHANNEL_PATTERN.fullmatch(raw_text)
        or (
            had_greeting_preface
            and (
                not greeting_substantive
                or _GREETING_CHECKIN_PATTERN.fullmatch(
                    greeting_substantive
                )
            )
        )
    )

    detailed_match = bool(
        classification_text
        and (
            _DETAILED_PATTERN.search(classification_text)
            or _EXACT_SENTENCE_COUNT_PATTERN.search(classification_text)
            or (
                word_total >= 8
                and _MULTI_PART_QUESTION_PATTERN.search(classification_text)
            )
            or word_total >= 24
        )
    )

    directive_match = bool(
        classification_text
        and not detailed_match
        and (
            _COMMAND_PATTERN.search(classification_text)
            or _DIRECTED_REQUEST_PATTERN.search(classification_text)
        )
    )

    personal_update_match = bool(
        classification_text
        and "?" not in classification_text
        and 3 <= word_total <= 24
        and not _COMMAND_PATTERN.search(classification_text)
        and not _DIRECTED_REQUEST_PATTERN.search(classification_text)
        and not _DETAILED_PATTERN.search(classification_text)
        and (
            _IMPLIED_I_ACTION_PATTERN.search(classification_text)
            or (
                _PERSONAL_UPDATE_START_PATTERN.search(classification_text)
                and _DECLARATIVE_VERB_PATTERN.search(classification_text)
            )
        )
    )

    ambiguous_fragment_match = bool(
        classification_text
        and "?" not in classification_text
        and not greeting_match
        and not personal_update_match
        and not _COMMAND_PATTERN.search(classification_text)
        and not detailed_match
        and word_total <= 4
    )

    explicit_recall_match = bool(
        looks_like_personal_fact_question(lowered)
        or any(
            re.search(pattern, lowered, flags=re.IGNORECASE)
            for pattern in _RECALL_QUERY_PATTERNS
        )
    )


    match True:
        # Begin:: Checking invalid input
        case _ if not raw_text:
            return InputRoute("invalid", lowered, reason="empty")

        case _ if len(raw_text) > 1000:
            return InputRoute("invalid", lowered, reason="too_long")

        case _ if not any(character.isalnum() for character in raw_text):
            return InputRoute("invalid", lowered, reason="punctuation_only")
        # End:: Checking invalid input

        # Begin:: Checking exit commands
        case _ if lowered in {"q", "quit", "exit"}:
            return InputRoute("exit", lowered, reason="exit_command")
        # End:: Checking exit commands

        # Begin:: Checking short hello/hi greeting
        case _ if hard_greeting:
            return InputRoute(
                "greeting",
                lowered,
                reason="leading_hello_or_hi",
            )
        # End:: Checking short hello/hi greeting

        # Begin:: Checking direct memory correction
        case _ if correction is not None:
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
        case _ if looks_like_perspective_correction(lowered):
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
        case _ if explicit_memory_store is not None:
            return InputRoute(
                "acknowledge",
                lowered,
                reason="explicit_memory_store",
                store_recall=True,
                recall_storage_text=explicit_memory_store,
            )
        # End:: Checking explicit memory storage command

        # Begin:: Checking explicit recall
        case _ if explicit_recall_match:
            return InputRoute(
                "recall",
                lowered,
                reason="explicit_recall",
                retrieve_recall=True,
                explicit_recall=True,
                allow_weak_match=True,
            )
        # End:: Checking explicit recall

        # Begin:: Checking answer to Nancee's previous question
        case _ if contextual_memory is not None:
            return InputRoute(
                "clarify",
                lowered,
                reason="contextual_answer",
                store_recall=True,
                recall_storage_text=contextual_memory,
                force_keep_history=True,
            )
        # End:: Checking answer to Nancee's previous question

        # Begin:: Checking greeting or backchannel
        case _ if greeting_match:
            return InputRoute("greeting", lowered, reason="greeting_or_backchannel")
        # End:: Checking greeting or backchannel

        # Begin:: Checking detailed request
        case _ if detailed_match:
            return InputRoute(
                "detailed",
                lowered,
                reason="detailed_request",
                retrieve_recall=question_like,
                store_recall=True,
                recall_storage_text=raw_text,
            )
        # End:: Checking detailed request

        # Begin:: Checking directive
        case _ if directive_match:
            return InputRoute("directive", lowered, reason="directive")
        # End:: Checking directive

        # Begin:: Checking complete personal update
        case _ if complete_statement or personal_update_match:
            return InputRoute(
                "acknowledge",
                lowered,
                reason="complete_personal_update",
                store_recall=storable_memory_text is not None,
                recall_storage_text=storable_memory_text,
            )
        # End:: Checking complete personal update

        # Begin:: Checking incomplete personal fact or ambiguous fragment
        case _ if personal_fact_fragment or ambiguous_fragment_match:
            return InputRoute(
                "clarify",
                lowered,
                reason=(
                    "personal_fact_fragment"
                    if personal_fact_fragment
                    else "ambiguous_fragment"
                ),
                retrieve_recall=personal_fact_fragment,
            )
        # End:: Checking incomplete personal fact or ambiguous fragment

        # Begin:: Checking ordinary question
        case _ if question_like:
            return InputRoute(
                "normal",
                lowered,
                reason="ordinary_question",
                retrieve_recall=True,
                store_recall=storable_memory_text is not None,
                recall_storage_text=storable_memory_text,
            )
        # End:: Checking ordinary question

        # Begin:: Default model route
        case _:
            return InputRoute(
                "normal",
                lowered,
                reason="default_model_route",
                store_recall=storable_memory_text is not None,
                recall_storage_text=storable_memory_text,
            )
        # End:: Default model route
