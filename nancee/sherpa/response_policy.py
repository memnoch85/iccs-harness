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


_LEADING_GREETING_TOKEN = re.compile(
    r"^(?:good morning|good afternoon|good evening|"
    r"hello|hi|hey|nancy|nancee|"
    r"so|well|okay|ok|and|yeah|yep|yup|uh|um|hmm|"
    r"man|dude|bruh)\b[\s,!.:;\-]*",
    flags=re.IGNORECASE,
)

_GREETING_CHECKIN_PATTERN = re.compile(
    r"^(?:how are you|how's it going|how is it going|"
    r"what's up|what is up|you there)\??[.! ]*$",
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
    r"^(?:tell me|show me|give me|help me|please|can you|could you|would you|"
    r"remind me|name|set|start|stop|open|close|play|pause|call|send)\b",
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
    r"am|was|were|have|had|own|drive|like|love|hate|prefer|use|work|live|"
    r"need|want|bought|buy|got|went|saw|finished|started|made|found|ordered|"
    r"picked|feel|felt|think|believe|plan|submitted|applied|installed|built|"
    r"lost|won|called|met|watched|ate|drank|parked|winding|sucked|hurt|"
    r"arrived|left|returned|received|completed|wired"
    r")\b",
    flags=re.IGNORECASE,
)


def _normalize(text):
    return re.sub(r"\s+", " ", str(text).strip())


def _word_count(text):
    return len(re.findall(r"\b[\w']+\b", str(text)))


def _strip_leading_greeting_preface(text):
    remaining = _normalize(text)
    removed = False

    while remaining:
        match = _LEADING_GREETING_TOKEN.match(remaining)

        if match is None:
            break

        removed = True
        remaining = remaining[match.end():].lstrip()

    return remaining, removed


def _classification_text(user_text):
    substantive, _ = _strip_leading_greeting_preface(user_text)
    return substantive or _normalize(user_text)


def looks_like_greeting_or_backchannel(user_text):
    text = _normalize(user_text)

    if _BACKCHANNEL_PATTERN.fullmatch(text):
        return True

    substantive, had_greeting = _strip_leading_greeting_preface(text)

    if not had_greeting:
        return False

    return (
        not substantive
        or bool(_GREETING_CHECKIN_PATTERN.fullmatch(substantive))
    )


def looks_like_detailed_request(user_text):
    text = _classification_text(user_text)

    if not text:
        return False

    if _DETAILED_PATTERN.search(text):
        return True

    if _EXACT_SENTENCE_COUNT_PATTERN.search(text):
        return True

    if (
        _word_count(text) >= 8
        and _MULTI_PART_QUESTION_PATTERN.search(text)
    ):
        return True

    return _word_count(text) >= 24


def looks_like_simple_personal_update(user_text):
    text = _classification_text(user_text)

    if not text or "?" in text:
        return False

    if _word_count(text) < 3 or _word_count(text) > 24:
        return False

    if _COMMAND_PATTERN.search(text):
        return False

    if _DETAILED_PATTERN.search(text):
        return False

    if _IMPLIED_I_ACTION_PATTERN.search(text):
        return True

    if not _PERSONAL_UPDATE_START_PATTERN.search(text):
        return False

    return bool(_DECLARATIVE_VERB_PATTERN.search(text))


def looks_like_ambiguous_fragment(user_text):
    text = _classification_text(user_text)

    if not text or "?" in text:
        return False

    if looks_like_greeting_or_backchannel(user_text):
        return False

    if looks_like_simple_personal_update(user_text):
        return False

    if _COMMAND_PATTERN.search(text):
        return False

    if looks_like_detailed_request(user_text):
        return False

    return _word_count(text) <= 4


def select_response_policy(user_text, *, authoritative_context_found=False):
    if authoritative_context_found:
        return ResponsePolicy(
            name="recall",
            temperature=RESPONSE_RECALL_TEMPERATURE,
            num_predict=RESPONSE_RECALL_NUM_PREDICT,
            instruction=(
                "Answer only the requested user fact in one short sentence. "
                "Use only the retrieved or confirmed fact. Never infer, embellish, "
                "or add a second fact. Do not add a follow-up question, commentary, "
                "apology, advice, or customer-service closing."
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

    if looks_like_detailed_request(user_text):
        return ResponsePolicy(
            name="detailed",
            temperature=RESPONSE_DETAILED_TEMPERATURE,
            num_predict=RESPONSE_DETAILED_NUM_PREDICT,
            instruction=(
                "Follow any exact sentence-count request from the user. Otherwise, "
                "give a concise but complete explanation in two to four short "
                "sentences. Use the extra space only for information needed to "
                "answer the question. Do not add a follow-up question or "
                "customer-service closing."
            ),
            drop_history=False,
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

