from __future__ import annotations

from dataclasses import dataclass

from memory_policy import (
    extract_explicit_memory_store_payload,
    extract_pending_memory_topic,
    extract_simple_fact_correction,
    extract_storable_memory_text,
    resolve_contextual_answer_memory,
)
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


def normalize_user_text(user_text: str) -> str:
    return " ".join(str(user_text).strip().lower().split())


def _reason(result: RouterMonResult) -> str:
    return f"{result.source}:{result.intent}:{result.confidence:.3f}"


def _route_from_router_mon(
    raw_text: str,
    lowered: str,
    result: RouterMonResult,
    *,
    previous_turn: dict[str, str] | None = None,
) -> InputRoute:
    """Translate one routerMon class into runtime metadata.

    This function does not reclassify the utterance. Any parsing below is
    post-route extraction/storage bookkeeping after routerMon has selected the
    route kind.
    """
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
        correction = extract_simple_fact_correction(raw_text)
        storage_text = None

        if correction is None:
            storage_text = (
                extract_explicit_memory_store_payload(raw_text)
                or extract_storable_memory_text(raw_text)
                or raw_text
            )

        return InputRoute(
            "memory_store",
            lowered,
            reason=reason,
            store_recall=correction is None,
            recall_storage_text=storage_text,
            force_keep_history=correction is not None,
            correction=correction,
        )

    if intent == "question":
        storable_memory_text = extract_storable_memory_text(raw_text)

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
            store_recall=storable_memory_text is not None,
            recall_storage_text=storable_memory_text,
        )

    if intent == "directive":
        return InputRoute(
            "directive",
            lowered,
            reason=reason,
            pending_memory_topic=extract_pending_memory_topic(raw_text),
        )

    if intent == "clarify":
        contextual_memory = resolve_contextual_answer_memory(
            raw_text,
            previous_turn,
        )

        return InputRoute(
            "clarify",
            lowered,
            reason=reason,
            store_recall=contextual_memory is not None,
            recall_storage_text=contextual_memory,
            force_keep_history=True,
        )

    if intent == "greeting":
        return InputRoute(
            "greeting",
            lowered,
            reason=reason,
            skip_latency_bridge=True,
        )

    if intent in {"affirmative", "negative"}:
        contextual_memory = resolve_contextual_answer_memory(
            raw_text,
            previous_turn,
        )

        return InputRoute(
            intent,
            lowered,
            reason=reason,
            store_recall=contextual_memory is not None,
            recall_storage_text=contextual_memory,
            force_keep_history=contextual_memory is not None,
        )

    if intent == "farewell":
        return InputRoute("farewell", lowered, reason=reason)

    if intent == "normal":
        storable_memory_text = extract_storable_memory_text(raw_text)

        return InputRoute(
            "normal",
            lowered,
            reason=reason,
            store_recall=storable_memory_text is not None,
            recall_storage_text=storable_memory_text,
        )

    raise RuntimeError(f"Unsupported routerMon intent: {intent!r}")


def route_user_input(
    user_text: str,
    *,
    previous_turn: dict[str, str] | None = None,
) -> InputRoute:
    raw_text = str(user_text).strip()
    lowered = normalize_user_text(raw_text)

    # Input validity and process control are not conversational routing.
    if not raw_text:
        return InputRoute("invalid", lowered, reason="empty")

    if len(raw_text) > 1000:
        return InputRoute("invalid", lowered, reason="too_long")

    if not any(character.isalnum() for character in raw_text):
        return InputRoute("invalid", lowered, reason="punctuation_only")

    if lowered in {"q", "quit", "exit"}:
        return InputRoute("exit", lowered, reason="exit_command")

    # routerMon owns every conversational route decision.
    result = classify_router_mon(raw_text)

    return _route_from_router_mon(
        raw_text,
        lowered,
        result,
        previous_turn=previous_turn,
    )
