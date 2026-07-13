from dataclasses import dataclass
import re

from config import (
    RESPONSE_ACK_NUM_PREDICT,
    RESPONSE_ACK_TEMPERATURE,
    RESPONSE_CLARIFY_NUM_PREDICT,
    RESPONSE_CLARIFY_TEMPERATURE,
    RESPONSE_DETAILED_NUM_PREDICT,
    RESPONSE_DETAILED_TEMPERATURE,
    RESPONSE_GREETING_NUM_PREDICT,
    RESPONSE_GREETING_TEMPERATURE,
    RESPONSE_NORMAL_NUM_PREDICT,
    RESPONSE_NORMAL_TEMPERATURE,
    RESPONSE_RECALL_NUM_PREDICT,
    RESPONSE_RECALL_TEMPERATURE,
)


@dataclass(frozen=True)
class ResponsePolicy:
    name: str
    temperature: float
    num_predict: int
    instruction: str
    drop_history: bool = False


_GREETING_PATTERN = re.compile(
    r"^(?:(?:nancy|nancee)[,\s]+)?"
    r"(?:hello|hi|hey|good morning|good afternoon|good evening)\b",
    flags=re.IGNORECASE,
)

_BACKCHANNEL_PATTERN = re.compile(
    r"^(?:okay|ok|alright|right|sure|thanks|thank you|sounds good|got it|cool)"
    r"[.! ]*$",
    flags=re.IGNORECASE,
)

_DETAILED_PATTERN = re.compile(
    r"\b(?:"
    r"explain|walk me through|step by step|in detail|detailed|deep dive|"
    r"why does|why do|why is|how does|how do|compare|difference between|"
    r"what causes|diagnose|troubleshoot|reason through|break down"
    r")\b",
    flags=re.IGNORECASE,
)

_COMMAND_PATTERN = re.compile(
    r"^(?:(?:nancy|nancee)[,\s]+)?(?:"
    r"tell me|show me|give me|help me|please|can you|could you|would you|"
    r"remind me|set|start|stop|open|close|play|pause|call|send"
    r")\b",
    flags=re.IGNORECASE,
)

_PERSONAL_UPDATE_START_PATTERN = re.compile(
    r"^(?:(?:nancy|nancee)[,\s]+)?(?:"
    r"i\b|i'm\b|i’ve\b|i've\b|i just\b|my\b|we\b|we're\b|we've\b|"
    r"today\b|this morning\b|this afternoon\b|tonight\b"
    r")",
    flags=re.IGNORECASE,
)

_DECLARATIVE_VERB_PATTERN = re.compile(
    r"\b(?:"
    r"am|was|were|have|had|own|drive|like|love|hate|prefer|use|work|live|"
    r"need|want|bought|buy|got|went|saw|finished|started|made|found|ordered|"
    r"picked|feel|felt|think|believe|plan|submitted|applied|installed|built|"
    r"lost|won|called|met|watched|ate|drank|parked|winding|sucked|hurt|"
    r"arrived|left|returned|received"
    r")\b",
    flags=re.IGNORECASE,
)


def _normalize(text):
    return re.sub(
        r"\s+",
        " ",
        str(text).strip(),
    )


def _word_count(text):
    return len(
        re.findall(
            r"\b[\w']+\b",
            str(text),
        )
    )


def looks_like_greeting_or_backchannel(user_text):
    text = _normalize(user_text)

    return bool(
        _GREETING_PATTERN.search(text)
        or _BACKCHANNEL_PATTERN.fullmatch(text)
    )


def looks_like_detailed_request(user_text):
    text = _normalize(user_text)

    return bool(
        _DETAILED_PATTERN.search(text)
        or _word_count(text) >= 24
    )


def looks_like_simple_personal_update(user_text):
    text = _normalize(user_text)

    if not text or "?" in text:
        return False

    if _word_count(text) < 3 or _word_count(text) > 24:
        return False

    if _COMMAND_PATTERN.search(text):
        return False

    if _DETAILED_PATTERN.search(text):
        return False

    if not _PERSONAL_UPDATE_START_PATTERN.search(text):
        return False

    return bool(
        _DECLARATIVE_VERB_PATTERN.search(text)
    )


def looks_like_ambiguous_fragment(user_text):
    text = _normalize(user_text)

    if not text or "?" in text:
        return False

    if looks_like_greeting_or_backchannel(text):
        return False

    if looks_like_simple_personal_update(text):
        return False

    return _word_count(text) <= 4


def select_response_policy(
    user_text,
    *,
    authoritative_context_found=False,
):
    if authoritative_context_found:
        return ResponsePolicy(
            name="recall",
            temperature=RESPONSE_RECALL_TEMPERATURE,
            num_predict=RESPONSE_RECALL_NUM_PREDICT,
            instruction=(
                "Answer only the requested user fact in one short sentence. "
                "Do not add a follow-up question, commentary, apology, advice, "
                "or customer-service closing."
            ),
            drop_history=True,
        )

    if looks_like_greeting_or_backchannel(user_text):
        return ResponsePolicy(
            name="greeting",
            temperature=RESPONSE_GREETING_TEMPERATURE,
            num_predict=RESPONSE_GREETING_NUM_PREDICT,
            instruction=(
                "Reply like a familiar passenger in one short sentence, usually "
                "four to twelve words. Speak only to the current user. Never "
                "mention listeners, an audience, users, customers, or clients. "
                "Do not use a customer-service closing."
            ),
            drop_history=False,
        )

    if looks_like_simple_personal_update(user_text):
        return ResponsePolicy(
            name="acknowledge",
            temperature=RESPONSE_ACK_TEMPERATURE,
            num_predict=RESPONSE_ACK_NUM_PREDICT,
            instruction=(
                "The user just shared a simple personal update. Give one natural "
                "acknowledgment of four to twelve words, then stop. Do not claim "
                "you were there, do not invent shared history, do not repeat the "
                "whole update, do not give advice, and do not ask a follow-up."
            ),
            drop_history=True,
        )

    if looks_like_ambiguous_fragment(user_text):
        return ResponsePolicy(
            name="clarify",
            temperature=RESPONSE_CLARIFY_TEMPERATURE,
            num_predict=RESPONSE_CLARIFY_NUM_PREDICT,
            instruction=(
                "The message may be incomplete or mistranscribed. Ask the user to "
                "repeat or clarify it in one short sentence. Do not guess what it "
                "means and do not discuss unrelated driving topics."
            ),
            drop_history=True,
        )

    if looks_like_detailed_request(user_text):
        return ResponsePolicy(
            name="detailed",
            temperature=RESPONSE_DETAILED_TEMPERATURE,
            num_predict=RESPONSE_DETAILED_NUM_PREDICT,
            instruction=(
                "Give a concise but complete explanation in two to four short "
                "sentences. Use the extra space only for information needed to "
                "answer the question. Do not add a customer-service closing."
            ),
            drop_history=False,
        )

    return ResponsePolicy(
        name="normal",
        temperature=RESPONSE_NORMAL_TEMPERATURE,
        num_predict=RESPONSE_NORMAL_NUM_PREDICT,
        instruction=(
            "Answer directly in one to three short sentences. Match the amount of "
            "detail to the question. Do not automatically ask a follow-up and do "
            "not add a customer-service closing."
        ),
        drop_history=False,
    )
