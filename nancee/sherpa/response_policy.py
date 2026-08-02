from __future__ import annotations

from dataclasses import dataclass

from config import (
    RESPONSE_ACK_NUM_PREDICT,
    RESPONSE_ACK_TEMPERATURE,
    RESPONSE_CLARIFY_NUM_PREDICT,
    RESPONSE_CLARIFY_TEMPERATURE,
    RESPONSE_DETAILED_NUM_PREDICT,
    RESPONSE_DETAILED_TEMPERATURE,
    RESPONSE_DIRECTIVE_NUM_PREDICT,
    RESPONSE_DIRECTIVE_TEMPERATURE,
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
    """Map one selected input route to generation settings."""



    # A missing fact cannot follow the same instruction as a found fact.
    if fact_miss:
        return ResponsePolicy(
            name="recall",
            temperature=RESPONSE_RECALL_TEMPERATURE,
            num_predict=RESPONSE_RECALL_NUM_PREDICT,
            instruction="Say you do not remember in four to six words.",
        )

    if authoritative_context_found or route_kind == "recall":
        return ResponsePolicy(
            name="recall",
            temperature=RESPONSE_RECALL_TEMPERATURE,
            num_predict=RESPONSE_RECALL_NUM_PREDICT,
            instruction="Return only the supplied fact. Keep it brief.",
        )

    if route_kind == "greeting":
        return ResponsePolicy(
            name="greeting",
            temperature=RESPONSE_GREETING_TEMPERATURE,
            num_predict=RESPONSE_GREETING_NUM_PREDICT,
            instruction="Reply warmly in one to four words.",
        )

    if route_kind == "directive":
        return ResponsePolicy(
            name="directive",
            temperature=RESPONSE_DIRECTIVE_TEMPERATURE,
            num_predict=RESPONSE_DIRECTIVE_NUM_PREDICT,
            instruction=(
                "Follow the command. For 'ask me,' output only the question; "
                "preserve wording except pronouns."
            ),
        )

    if route_kind == "acknowledge":
        return ResponsePolicy(
            name="acknowledge",
            temperature=RESPONSE_ACK_TEMPERATURE,
            num_predict=RESPONSE_ACK_NUM_PREDICT,
            instruction=(
                "Acknowledge naturally in four to nine words. Invent nothing."
            ),
        )

    if route_kind == "detailed":
        return ResponsePolicy(
            name="detailed",
            temperature=RESPONSE_DETAILED_TEMPERATURE,
            num_predict=RESPONSE_DETAILED_NUM_PREDICT,
            instruction=(
                "Honor requested length. Otherwise use two to four short sentences."
            ),
        )

    if route_kind == "clarify":
        return ResponsePolicy(
            name="clarify",
            temperature=RESPONSE_CLARIFY_TEMPERATURE,
            num_predict=RESPONSE_CLARIFY_NUM_PREDICT,
            instruction=(
                "Use the previous turn. Acknowledge answers; otherwise ask "
                "one short question."
            ),
        )

    return ResponsePolicy(
        name="normal",
        temperature=RESPONSE_NORMAL_TEMPERATURE,
        num_predict=RESPONSE_NORMAL_NUM_PREDICT,
        instruction="",
    )
