from __future__ import annotations

from dataclasses import dataclass

from config import (
    RESPONSE_ACK_NUM_PREDICT,
    RESPONSE_ACK_TEMPERATURE,
    RESPONSE_CLARIFY_NUM_PREDICT,
    RESPONSE_CLARIFY_TEMPERATURE,
    RESPONSE_DIRECTIVE_NUM_PREDICT,
    RESPONSE_DIRECTIVE_TEMPERATURE,
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


def response_policy_for_route(
    route_kind: str,
    *,
    authoritative_context_found: bool = False,
    fact_miss: bool = False,
) -> ResponsePolicy:
    """Map one already-selected input route to generation settings."""
    if route_kind == "speaker_return":
        return ResponsePolicy(
            name="speaker_return",
            temperature=RESPONSE_ACK_TEMPERATURE,
            num_predict=RESPONSE_ACK_NUM_PREDICT,
            instruction=(
                "The primary speaker has returned. Welcome them back naturally "
                "in one short sentence, then stop. Do not mention memory, prior "
                "conversation, uncertainty, or ask a question."
            ),
            drop_history=False,
        )

    if route_kind == "speaker":
        return ResponsePolicy(
            name="speaker",
            temperature=RESPONSE_RECALL_TEMPERATURE,
            num_predict=RESPONSE_RECALL_NUM_PREDICT,
            instruction=(
                "Answer who is currently speaking in one short sentence. "
                "Use only the supplied ACTIVE SPEAKER session state. "
                "Do not substitute the primary user's profile identity."
            ),
            drop_history=False,
        )

    if authoritative_context_found or fact_miss or route_kind == "recall":
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
            drop_history=False,
        )

    if route_kind == "greeting":
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

    if route_kind == "directive":
        return ResponsePolicy(
            name="directive",
            temperature=RESPONSE_DIRECTIVE_TEMPERATURE,
            num_predict=RESPONSE_DIRECTIVE_NUM_PREDICT,
            instruction=(
                "Execute the command. For ask-me commands, output only "
                "the question. Preserve nouns, articles, and ownership; "
                "change only speaker pronouns."
            ),
            drop_history=False,
        )

    if route_kind == "acknowledge":
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
            drop_history=False,
        )

    if route_kind == "detailed":
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

    if route_kind == "clarify":
        return ResponsePolicy(
            name="clarify",
            temperature=RESPONSE_CLARIFY_TEMPERATURE,
            num_predict=RESPONSE_CLARIFY_NUM_PREDICT,
            instruction=(
                "Use the previous exchange. If this answers your last question, "
                "acknowledge the answer briefly and stop. Otherwise ask one brief "
                "clarification."
            ),
            drop_history=False,
        )

    return ResponsePolicy(
        name="normal",
        temperature=RESPONSE_NORMAL_TEMPERATURE,
        num_predict=RESPONSE_NORMAL_NUM_PREDICT,
        instruction=(
            "Answer the current message naturally. Use the previous exchange and "
            "any supplied relevant memory when helpful. If no memory was supplied, "
            "answer from general knowledge rather than treating it as a memory "
            "failure. Follow direct requests exactly and be brief."
        ),
        drop_history=False,
    )
