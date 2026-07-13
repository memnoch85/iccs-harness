#!/usr/bin/env python3
"""
Unattended NANCEE response-tunable benchmark.

This does NOT start ASR, TTS, sounddevice, or nancee_chat.py.
It drives the current Ollama, response-policy, memory, perspective-repair,
and authoritative-response modules directly with text prompts.

Default run:
    python3 test/benchmark/bench_nancee_unattended.py --minutes 110

Outputs:
    test/benchmark/results/unattended_<timestamp>/
        turns.csv
        turns.jsonl
        leaderboard.md
        summary.json
        responses.md
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import inspect
import io
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[2]
SHERPA_DIR = PROJECT_ROOT / "sherpa"

if str(SHERPA_DIR) not in sys.path:
    sys.path.insert(0, str(SHERPA_DIR))

# These imports intentionally avoid nancee_chat.py so no audio stack starts.
from authoritative_response import prepare_authoritative_response
from config import (
    LLM_MODEL,
    MEMORY_RECALL_CONTEXT_MAX_CHARACTERS,
    MEMORY_RECALL_LIMIT,
    MEMORY_RECALL_MIN_SCORE,
    MEMORY_RECALL_SNIPPET_WORDS,
    MEMORY_RECALL_TURN_LIMIT,
    MEMORY_RECENT_PROMPT_TURNS,
)
from memory_policy import (
    is_complete_memory_statement,
    memory_storage_skip_reason,
)
from ollama_runtime import (
    ensure_ollama_model_loaded,
    prime_ollama_context,
    stream_ollama_response,
)
from recall_policy import repair_recall_perspective
from response_policy import select_response_policy
from session_archive import SessionArchive
from short_term_memory import ShortTermMemory


@dataclass(frozen=True)
class Profile:
    name: str
    normal_temperature: float
    normal_num_predict: int
    detailed_temperature: float
    detailed_num_predict: int
    recall_temperature: float
    recall_num_predict: int
    description: str


PROFILES: dict[str, Profile] = {
    "A": Profile(
        name="A",
        normal_temperature=0.30,
        normal_num_predict=36,
        detailed_temperature=0.30,
        detailed_num_predict=65,
        recall_temperature=0.15,
        recall_num_predict=18,
        description="Current baseline",
    ),
    "B": Profile(
        name="B",
        normal_temperature=0.20,
        normal_num_predict=48,
        detailed_temperature=0.20,
        detailed_num_predict=80,
        recall_temperature=0.10,
        recall_num_predict=18,
        description="Conservative and complete",
    ),
    "C": Profile(
        name="C",
        normal_temperature=0.25,
        normal_num_predict=44,
        detailed_temperature=0.25,
        detailed_num_predict=72,
        recall_temperature=0.12,
        recall_num_predict=18,
        description="Balanced",
    ),
    "D": Profile(
        name="D",
        normal_temperature=0.28,
        normal_num_predict=48,
        detailed_temperature=0.25,
        detailed_num_predict=84,
        recall_temperature=0.12,
        recall_num_predict=20,
        description="Natural but completion-biased",
    ),
}


@dataclass(frozen=True)
class BenchCase:
    case_id: str
    prompts: tuple[str, ...]
    kind: str
    expected_policy: str | None = None
    should_store: bool = False
    retrieve_memory: bool = False
    profile_key: str | None = None
    profile_value: str | None = None
    fact_miss: bool = False
    max_words: int | None = None

    def prompt_for_round(self, round_index: int) -> str:
        return self.prompts[round_index % len(self.prompts)]


CASES: tuple[BenchCase, ...] = (
    BenchCase(
        case_id="seed_bag",
        prompts=(
            "Hey Nancee, I bought a green duffel bag at Target today.",
            "Nancee, today I bought a green duffel bag from Target.",
            "Hey, I picked up a green duffel bag at Target today.",
            "Today I bought a green duffel bag at Target.",
        ),
        kind="update",
        expected_policy="acknowledge",
        should_store=True,
        max_words=20,
    ),
    BenchCase(
        case_id="seed_can",
        prompts=(
            "I finished soldering a CAN transceiver yesterday.",
            "Yesterday I finished soldering a CAN transceiver.",
            "Hey man, I finished soldering a CAN transceiver yesterday.",
            "I got the CAN transceiver soldered yesterday.",
        ),
        kind="update",
        expected_policy="acknowledge",
        should_store=True,
        max_words=20,
    ),
    BenchCase(
        case_id="profile_name",
        prompts=(
            "What is my name?",
            "Nancee, what is my name?",
            "Who am I?",
            "Can you tell me my name?",
        ),
        kind="profile",
        expected_policy="recall",
        profile_key="name",
        profile_value="Anders",
        max_words=12,
    ),
    BenchCase(
        case_id="recall_bag",
        prompts=(
            "What did I buy at Target?",
            "What did I get from Target today?",
            "What kind of bag did I buy at Target?",
            "What did I purchase at Target?",
        ),
        kind="recall",
        expected_policy="recall",
        retrieve_memory=True,
        max_words=16,
    ),
    BenchCase(
        case_id="recall_can",
        prompts=(
            "What did I finish soldering?",
            "What component did I solder yesterday?",
            "What was I soldering yesterday?",
            "What did I get soldered?",
        ),
        kind="recall",
        expected_policy="recall",
        retrieve_memory=True,
        max_words=18,
    ),
    BenchCase(
        case_id="unknown_sister",
        prompts=(
            "What is my sister's middle name?",
            "Do you remember my sister's middle name?",
            "What middle name does my sister have?",
            "Tell me my sister's middle name.",
        ),
        kind="fact_miss",
        expected_policy="recall",
        fact_miss=True,
        max_words=14,
    ),
    BenchCase(
        case_id="correct_bag",
        prompts=(
            "Actually, the duffel bag was blue, not green.",
            "Correction, that duffel bag was blue rather than green.",
            "I need to correct that: the duffel bag was blue, not green.",
            "Actually it was a blue duffel bag, not a green one.",
        ),
        kind="correction",
        expected_policy="acknowledge",
        should_store=True,
        max_words=20,
    ),
    BenchCase(
        case_id="recall_color",
        prompts=(
            "What color was the duffel bag?",
            "What was the duffel bag's color?",
            "Was the duffel bag green or blue?",
            "Which color duffel bag did I buy?",
        ),
        kind="recall",
        expected_policy="recall",
        retrieve_memory=True,
        max_words=16,
    ),
    BenchCase(
        case_id="ownership",
        prompts=(
            "Did you buy the duffel bag, or did I?",
            "Was it you or me who bought the duffel bag?",
            "Who bought that duffel bag, you or I?",
            "Did I buy the bag, or did you?",
        ),
        kind="recall",
        expected_policy="recall",
        retrieve_memory=True,
        max_words=18,
    ),
    BenchCase(
        case_id="capital_france",
        prompts=(
            "What is the capital of France?",
            "Name France's capital.",
            "Which city is the capital of France?",
            "Tell me the capital city of France.",
        ),
        kind="knowledge",
        expected_policy="normal",
        max_words=18,
    ),
    BenchCase(
        case_id="turbocharger",
        prompts=(
            "Explain in two sentences how a turbocharger works.",
            "In two sentences, explain how a turbocharger works.",
            "Briefly explain a turbocharger in two complete sentences.",
            "Give me a two-sentence explanation of how a turbo works.",
        ),
        kind="detailed",
        expected_policy="detailed",
        max_words=90,
    ),
    BenchCase(
        case_id="sauron_history",
        prompts=(
            "Give me a brief history of Sauron and state his relationship to Morgoth.",
            "Briefly explain Sauron's history and how he related to Morgoth.",
            "Who was Sauron, and what was his relationship with Morgoth?",
            "Summarize Sauron and his connection to Morgoth.",
        ),
        kind="knowledge",
        expected_policy="normal",
        max_words=70,
    ),
    BenchCase(
        case_id="sauron_correction",
        prompts=(
            "Morgoth was Sauron's master, right?",
            "Sauron served Morgoth, correct?",
            "Wasn't Morgoth the master and Sauron his servant?",
            "Morgoth outranked Sauron, didn't he?",
        ),
        kind="knowledge",
        expected_policy="normal",
        max_words=35,
    ),
    BenchCase(
        case_id="ambiguous_fragment",
        prompts=(
            "Hardly drive.",
            "Barely wired.",
            "Mostly solder.",
            "Probably backpack.",
        ),
        kind="clarify",
        expected_policy="clarify",
        should_store=False,
        max_words=18,
    ),
    BenchCase(
        case_id="seed_weird_name",
        prompts=(
            "My wife's name is I got 99 problems.",
            "Remember, my wife's name is I got 99 problems.",
            "My wife is named I got 99 problems.",
            "The name of my wife is I got 99 problems.",
        ),
        kind="update",
        expected_policy="acknowledge",
        should_store=True,
        max_words=20,
    ),
    BenchCase(
        case_id="recall_weird_name",
        prompts=(
            "What is my wife's name?",
            "Do you remember my wife's name?",
            "My wife's name.",
            "Who is my wife named?",
        ),
        kind="recall",
        expected_policy="recall",
        retrieve_memory=True,
        max_words=18,
    ),
)


@dataclass
class TurnResult:
    timestamp: str
    profile: str
    profile_description: str
    round_index: int
    case_id: str
    kind: str
    prompt: str
    response: str
    policy: str
    temperature: float
    num_predict: int
    first_token_s: float | None
    llm_total_s: float
    prompt_eval_s: float | None
    generation_s: float | None
    response_tokens: int | None
    done_reason: str | None
    word_count: int
    complete: bool
    retrieved_hits: int
    retrieved_context_chars: int
    stored: bool
    storage_skip_reason: str
    perspective_repaired: bool
    guard_action: str
    score: float
    hard_fail: bool
    flags: list[str]
    internal_log: str


def call_supported(function: Any, **kwargs: Any) -> Any:
    """Call a project function using only parameters its current version accepts."""
    signature = inspect.signature(function)
    accepted = {
        name: value
        for name, value in kwargs.items()
        if name in signature.parameters
    }
    return function(**accepted)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    weight = position - lower
    return (
        ordered[lower] * (1.0 - weight)
        + ordered[upper] * weight
    )


def choose_tunables(
    profile: Profile,
    policy_name: str,
) -> tuple[float, int]:
    if policy_name == "acknowledge":
        return 0.25, 18

    if policy_name == "greeting":
        return 0.30, 18

    if policy_name == "clarify":
        return 0.20, 14

    if policy_name == "recall":
        return (
            profile.recall_temperature,
            profile.recall_num_predict,
        )

    if policy_name == "detailed":
        return (
            profile.detailed_temperature,
            profile.detailed_num_predict,
        )

    return (
        profile.normal_temperature,
        profile.normal_num_predict,
    )


def parse_runtime_log(text: str) -> dict[str, Any]:
    done_reason = None
    prompt_eval_s = None
    generation_s = None
    response_tokens = None

    done_matches = re.findall(
        r"\[OLLAMA DONE\].*",
        text,
    )

    if done_matches:
        line = done_matches[-1]

        match = re.search(r"\breason=([A-Za-z0-9_]+)", line)
        if match:
            done_reason = match.group(1)

        match = re.search(r"\bprompt_eval=([0-9.]+)s", line)
        if match:
            prompt_eval_s = float(match.group(1))

        match = re.search(r"\bgeneration=([0-9.]+)s", line)
        if match:
            generation_s = float(match.group(1))

        match = re.search(r"\bresponse_tokens=(\d+)", line)
        if match:
            response_tokens = int(match.group(1))

    return {
        "done_reason": done_reason,
        "prompt_eval_s": prompt_eval_s,
        "generation_s": generation_s,
        "response_tokens": response_tokens,
    }


def response_is_complete(
    response: str,
    done_reason: str | None,
) -> bool:
    text = str(response).strip()

    if not text:
        return False

    if done_reason == "length":
        return False

    if text.count("(") != text.count(")"):
        return False

    if text.count("[") != text.count("]"):
        return False

    if re.search(r"[,;:({\[-]\s*$", text):
        return False

    if re.search(
        r"\b(?:and|or|but|because|with|without|to|of|the|a|an)\s*$",
        text,
        flags=re.IGNORECASE,
    ):
        return False

    return bool(
        re.search(
            r"""[.!?]["')\]]*$""",
            text,
        )
    )


def is_memory_miss(response: str) -> bool:
    return bool(
        re.search(
            r"\b(?:do not|don't|cannot|can't)\s+"
            r"(?:remember|recall)\b",
            response,
            flags=re.IGNORECASE,
        )
    )


def wrong_user_perspective(response: str) -> bool:
    text = response.strip()

    if is_memory_miss(text):
        return False

    return bool(
        re.match(
            r"^(?:actually[, ]+|today[, ]+|yesterday[, ]+)?"
            r"(?:i|i'm|i've|my|mine|me)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def shared_experience_hallucination(response: str) -> bool:
    text = response.lower()

    patterns = (
        r"\bwe\b.{0,50}\b(?:bought|picked|went|visited|wired|soldered|finished)\b",
        r"\bour\b.{0,40}\b(?:trip|shopping|commute|project|purchase)\b",
        r"\bwith you\b.{0,40}\b(?:bought|picked|went|visited|wired|soldered)\b",
        r"\bi remember (?:that|our) (?:trip|shopping|visit|commute)\b",
    )

    return any(
        re.search(pattern, text)
        for pattern in patterns
    )


def add_flag(
    flags: list[str],
    name: str,
    *,
    hard: bool = False,
) -> bool:
    flags.append(name)
    return hard


def score_turn(
    case: BenchCase,
    *,
    response: str,
    policy_name: str,
    stored: bool,
    retrieved_hits: int,
    perspective_repaired: bool,
    complete: bool,
    done_reason: str | None,
    first_token_s: float | None,
) -> tuple[float, bool, list[str]]:
    text = response.strip()
    lower = text.lower()
    score = 10.0
    hard_fail = False
    flags: list[str] = []

    def deduct(
        amount: float,
        flag: str,
        *,
        hard: bool = False,
    ) -> None:
        nonlocal score, hard_fail
        score -= amount
        flags.append(flag)
        hard_fail = hard_fail or hard

    if case.expected_policy and policy_name != case.expected_policy:
        deduct(
            1.0,
            f"policy_expected_{case.expected_policy}_got_{policy_name}",
        )

    if case.should_store and not stored:
        deduct(3.0, "required_memory_not_stored", hard=True)

    if not case.should_store and stored:
        deduct(3.0, "forbidden_fragment_stored", hard=True)

    if case.retrieve_memory and retrieved_hits == 0:
        deduct(4.0, "memory_recall_zero_hits", hard=True)

    if not complete:
        deduct(2.0, "incomplete_response", hard=True)

    if done_reason == "length":
        deduct(1.0, "token_limit_cutoff", hard=True)

    if case.max_words is not None:
        words = len(re.findall(r"\S+", text))
        if words > case.max_words:
            deduct(0.75, "response_too_long")

    if case.kind == "update":
        if "?" in text:
            deduct(1.0, "unnecessary_followup_question")

        if shared_experience_hallucination(text):
            deduct(4.0, "invented_shared_experience", hard=True)

    if case.case_id == "profile_name":
        if "anders" not in lower:
            deduct(4.0, "wrong_or_missing_profile_name", hard=True)

        if "nancee" in lower and "anders" not in lower:
            deduct(2.0, "assistant_name_used_as_user_name", hard=True)

    if case.case_id == "recall_bag":
        if "duffel" not in lower or "green" not in lower:
            deduct(3.0, "incorrect_bag_recall", hard=True)

    if case.case_id == "recall_can":
        has_can = bool(re.search(r"\bcan\b", lower))
        has_transceiver = "transceiver" in lower

        if not (has_can and has_transceiver):
            deduct(3.0, "incorrect_can_recall", hard=True)

    if case.case_id == "unknown_sister":
        if not is_memory_miss(text):
            deduct(5.0, "unknown_personal_fact_guessed", hard=True)

    if case.case_id == "recall_color":
        if "blue" not in lower:
            deduct(4.0, "newest_correction_not_used", hard=True)

    if case.case_id == "ownership":
        user_owned = (
            "you" in lower
            and not re.search(
                r"\b(?:i|me|my)\b.{0,20}\b(?:bought|purchased|owned)\b",
                lower,
            )
        )

        if not user_owned:
            deduct(4.0, "ownership_perspective_wrong", hard=True)

    if case.case_id == "capital_france":
        if "paris" not in lower:
            deduct(4.0, "capital_answer_wrong", hard=True)

    if case.case_id == "turbocharger":
        core_terms = sum(
            term in lower
            for term in (
                "exhaust",
                "turbine",
                "compress",
                "air",
            )
        )

        if core_terms < 3:
            deduct(3.0, "turbo_explanation_missing_core_mechanics")

    if case.case_id == "sauron_history":
        has_morgoth = "morgoth" in lower
        has_servant_relation = bool(
            re.search(
                r"\b(?:servant|lieutenant|served|follower|under)\b",
                lower,
            )
        )
        reversed_relation = bool(
            re.search(
                r"sauron.{0,40}master of morgoth"
                r"|morgoth.{0,40}(?:served|under|servant of).{0,20}sauron",
                lower,
            )
        )

        if not (has_morgoth and has_servant_relation):
            deduct(3.0, "sauron_relationship_missing_or_vague")

        if reversed_relation:
            deduct(5.0, "sauron_morgoth_relationship_reversed", hard=True)

    if case.case_id == "sauron_correction":
        has_both = (
            "morgoth" in lower
            and "sauron" in lower
        )
        confirms = bool(
            re.search(
                r"\b(?:yes|correct|right|indeed|served|master|lieutenant)\b",
                lower,
            )
        )
        reversed_relation = bool(
            re.search(
                r"sauron.{0,40}master of morgoth"
                r"|morgoth.{0,40}(?:served|under|servant of).{0,20}sauron",
                lower,
            )
        )

        if not (has_both and confirms):
            deduct(3.0, "correction_not_confirmed")

        if reversed_relation:
            deduct(5.0, "correction_repeats_reversed_relation", hard=True)

    if case.case_id == "ambiguous_fragment":
        clarification = bool(
            re.search(
                r"\b(?:repeat|clarify|mean|catch|understand|say that again)\b",
                lower,
            )
        ) or "?" in text

        if not clarification:
            deduct(3.0, "fragment_not_clarified")

    if case.case_id == "recall_weird_name":
        if "99 problems" not in lower:
            deduct(4.0, "weird_exact_fact_not_recalled", hard=True)

    if case.retrieve_memory and wrong_user_perspective(text):
        deduct(5.0, "wrong_first_person_reaches_output", hard=True)

    if perspective_repaired:
        # Correct output is what matters, but count model-side confusion.
        deduct(0.25, "perspective_required_repair")

    bad_service_phrases = (
        "how can i help",
        "need help with anything",
        "would you like me to",
        "our listeners",
        "for our listeners",
        "customer",
        "i'm here and ready",
    )

    if any(phrase in lower for phrase in bad_service_phrases):
        deduct(1.0, "customer_service_chatter")

    latency_limit = 8.0 if case.kind in {"recall", "profile", "detailed"} else 6.0

    if (
        first_token_s is not None
        and first_token_s > latency_limit
    ):
        deduct(0.5, "slow_first_token")

    return max(0.0, score), hard_fail, flags


def run_llm_turn(
    *,
    user_text: str,
    history: list[dict[str, str]],
    memory_context: str,
    retrieved_context: str,
    response_instruction: str,
    temperature: float,
    num_predict: int,
) -> tuple[str, float | None, float, str, dict[str, Any]]:
    kwargs = {
        "user_text": user_text,
        "history": history,
        "memory_context": memory_context,
        "retrieved_context": retrieved_context,
        "response_instruction": response_instruction,
        "temperature": temperature,
        "num_predict": num_predict,
    }

    signature = inspect.signature(
        stream_ollama_response
    )

    unsupported = [
        key
        for key in (
            "response_instruction",
            "temperature",
            "num_predict",
        )
        if key not in signature.parameters
    ]

    if unsupported:
        raise RuntimeError(
            "Current stream_ollama_response() is missing required "
            f"benchmark controls: {unsupported}. "
            "Do not run a tunable benchmark when the tunables cannot "
            "be passed per request."
        )

    output_capture = io.StringIO()
    tokens: list[str] = []
    first_token_s: float | None = None
    started = time.perf_counter()

    with contextlib.redirect_stdout(output_capture):
        response_iter = stream_ollama_response(
            **kwargs
        )

        for token in response_iter:
            if first_token_s is None:
                first_token_s = (
                    time.perf_counter()
                    - started
                )

            tokens.append(str(token))

    total_s = time.perf_counter() - started
    internal_log = output_capture.getvalue()
    parsed = parse_runtime_log(internal_log)

    return (
        "".join(tokens).strip(),
        first_token_s,
        total_s,
        internal_log,
        parsed,
    )


def retrieve_context(
    archive: SessionArchive,
    query: str,
) -> tuple[list[dict[str, Any]], str]:
    hits = call_supported(
        archive.retrieve,
        query=query,
        limit=MEMORY_RECALL_LIMIT,
        min_score=MEMORY_RECALL_MIN_SCORE,
        snippet_words=MEMORY_RECALL_SNIPPET_WORDS,
    )

    context = call_supported(
        archive.format_related_context,
        hits=hits,
        max_characters=MEMORY_RECALL_CONTEXT_MAX_CHARACTERS,
    )

    return list(hits or []), str(context or "")


def prepare_guarded_response(
    response: str,
    *,
    profile_hits: list[Any],
    fact_miss: bool,
    retrieved_context: str,
) -> tuple[str, str]:
    guarded = call_supported(
        prepare_authoritative_response,
        response_text=response,
        assistant_text=response,
        text=response,
        profile_hits=profile_hits,
        fact_miss=fact_miss,
        retrieved_context=retrieved_context,
    )

    if (
        isinstance(guarded, tuple)
        and len(guarded) >= 2
    ):
        return str(guarded[0]).strip(), str(guarded[1])

    return str(guarded).strip(), "accepted"


def run_case(
    *,
    profile: Profile,
    round_index: int,
    case: BenchCase,
    recent: ShortTermMemory,
    archive: SessionArchive,
) -> TurnResult:
    prompt = case.prompt_for_round(round_index)
    profile_hits: list[Any] = []
    memory_context = ""
    retrieved_context = ""
    retrieved_hits: list[dict[str, Any]] = []

    if case.profile_key and case.profile_value:
        profile_hits = [
            SimpleNamespace(
                key=case.profile_key,
                value=case.profile_value,
            )
        ]

        memory_context = (
            "Confirmed facts about the human user. "
            "Answer directly and do not mention this fact list.\n"
            f"- {case.profile_key}: {case.profile_value}"
        )

    elif case.fact_miss:
        memory_context = (
            "No matching confirmed fact about the human user "
            "was retrieved. Say only that you do not remember "
            "it yet."
        )

    elif case.retrieve_memory:
        retrieved_hits, retrieved_context = (
            retrieve_context(
                archive,
                prompt,
            )
        )

        if not retrieved_context.strip():
            memory_context = (
                "No matching confirmed fact about the human user "
                "was retrieved. Say only that you do not remember "
                "it yet."
            )

    authoritative_context_found = bool(
        memory_context.strip()
        or retrieved_context.strip()
    )

    policy = call_supported(
        select_response_policy,
        user_text=prompt,
        text=prompt,
        authoritative_context_found=(
            authoritative_context_found
        ),
    )

    policy_name = str(
        getattr(policy, "name", "normal")
    )

    temperature, num_predict = choose_tunables(
        profile,
        policy_name,
    )

    drop_history = bool(
        getattr(policy, "drop_history", False)
    )

    response_instruction = str(
        getattr(policy, "instruction", "")
    )

    history = (
        []
        if authoritative_context_found or drop_history
        else recent.get_messages()
    )

    (
        response,
        first_token_s,
        llm_total_s,
        internal_log,
        parsed,
    ) = run_llm_turn(
        user_text=prompt,
        history=history,
        memory_context=memory_context,
        retrieved_context=retrieved_context,
        response_instruction=response_instruction,
        temperature=temperature,
        num_predict=num_predict,
    )

    perspective_repaired = False

    if retrieved_context.strip():
        response, perspective_repaired = (
            repair_recall_perspective(
                response
            )
        )

    guard_action = "not_authoritative"

    if authoritative_context_found:
        response, guard_action = prepare_guarded_response(
            response,
            profile_hits=profile_hits,
            fact_miss=(
                case.fact_miss
                or (
                    case.retrieve_memory
                    and not retrieved_context.strip()
                )
            ),
            retrieved_context=retrieved_context,
        )

    should_store = is_complete_memory_statement(
        prompt
    )

    stored_id = None
    skip_reason = ""

    if should_store:
        stored_id = archive.add_turn(
            user_text=prompt,
            assistant_text="Okay.",
        )
    else:
        skip_reason = memory_storage_skip_reason(
            prompt
        )

    recent.add_turn(
        user_text=prompt,
        assistant_text=response or "Okay.",
    )

    done_reason = parsed["done_reason"]
    complete = response_is_complete(
        response,
        done_reason,
    )

    score, hard_fail, flags = score_turn(
        case,
        response=response,
        policy_name=policy_name,
        stored=stored_id is not None,
        retrieved_hits=len(retrieved_hits),
        perspective_repaired=perspective_repaired,
        complete=complete,
        done_reason=done_reason,
        first_token_s=first_token_s,
    )

    return TurnResult(
        timestamp=datetime.now().isoformat(
            timespec="seconds"
        ),
        profile=profile.name,
        profile_description=profile.description,
        round_index=round_index,
        case_id=case.case_id,
        kind=case.kind,
        prompt=prompt,
        response=response,
        policy=policy_name,
        temperature=temperature,
        num_predict=num_predict,
        first_token_s=first_token_s,
        llm_total_s=llm_total_s,
        prompt_eval_s=parsed["prompt_eval_s"],
        generation_s=parsed["generation_s"],
        response_tokens=parsed["response_tokens"],
        done_reason=done_reason,
        word_count=len(re.findall(r"\S+", response)),
        complete=complete,
        retrieved_hits=len(retrieved_hits),
        retrieved_context_chars=len(
            retrieved_context
        ),
        stored=stored_id is not None,
        storage_skip_reason=skip_reason,
        perspective_repaired=perspective_repaired,
        guard_action=guard_action,
        score=score,
        hard_fail=hard_fail,
        flags=flags,
        internal_log=internal_log,
    )


def write_jsonl(
    path: Path,
    result: TurnResult,
) -> None:
    with path.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(
                asdict(result),
                ensure_ascii=False,
            )
            + "\n"
        )


CSV_FIELDS = [
    "timestamp",
    "profile",
    "profile_description",
    "round_index",
    "case_id",
    "kind",
    "prompt",
    "response",
    "policy",
    "temperature",
    "num_predict",
    "first_token_s",
    "llm_total_s",
    "prompt_eval_s",
    "generation_s",
    "response_tokens",
    "done_reason",
    "word_count",
    "complete",
    "retrieved_hits",
    "retrieved_context_chars",
    "stored",
    "storage_skip_reason",
    "perspective_repaired",
    "guard_action",
    "score",
    "hard_fail",
    "flags",
]


def append_csv(
    path: Path,
    result: TurnResult,
) -> None:
    exists = path.exists()

    with path.open(
        "a",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
        )

        if not exists:
            writer.writeheader()

        row = asdict(result)
        row["flags"] = "|".join(result.flags)
        row.pop("internal_log", None)

        writer.writerow(
            {
                field: row.get(field)
                for field in CSV_FIELDS
            }
        )


def summarize(
    results: list[TurnResult],
) -> dict[str, Any]:
    profiles: dict[str, dict[str, Any]] = {}

    for profile_name in sorted(
        {result.profile for result in results}
    ):
        rows = [
            result
            for result in results
            if result.profile == profile_name
        ]

        first_tokens = [
            result.first_token_s
            for result in rows
            if result.first_token_s is not None
        ]

        totals = [
            result.llm_total_s
            for result in rows
        ]

        profiles[profile_name] = {
            "description": PROFILES[
                profile_name
            ].description,
            "turns": len(rows),
            "rounds": len(
                {
                    row.round_index
                    for row in rows
                }
            ),
            "average_score": (
                statistics.mean(
                    row.score for row in rows
                )
                if rows
                else 0.0
            ),
            "hard_fails": sum(
                row.hard_fail for row in rows
            ),
            "length_cutoffs": sum(
                row.done_reason == "length"
                for row in rows
            ),
            "incomplete_responses": sum(
                not row.complete for row in rows
            ),
            "zero_hit_recalls": sum(
                (
                    row.kind == "recall"
                    and row.retrieved_hits == 0
                )
                for row in rows
            ),
            "perspective_repairs": sum(
                row.perspective_repaired
                for row in rows
            ),
            "wrong_perspective_outputs": sum(
                "wrong_first_person_reaches_output"
                in row.flags
                for row in rows
            ),
            "hallucination_flags": sum(
                any(
                    flag in {
                        "invented_shared_experience",
                        "unknown_personal_fact_guessed",
                        "sauron_morgoth_relationship_reversed",
                        "correction_repeats_reversed_relation",
                        "ownership_perspective_wrong",
                    }
                    for flag in row.flags
                )
                for row in rows
            ),
            "first_token_average_s": (
                statistics.mean(first_tokens)
                if first_tokens
                else None
            ),
            "first_token_p95_s": percentile(
                first_tokens,
                0.95,
            ),
            "llm_total_average_s": (
                statistics.mean(totals)
                if totals
                else None
            ),
            "average_words": (
                statistics.mean(
                    row.word_count for row in rows
                )
                if rows
                else 0.0
            ),
        }

    ranking = sorted(
        profiles,
        key=lambda name: (
            profiles[name]["hard_fails"],
            profiles[name]["hallucination_flags"],
            profiles[name][
                "wrong_perspective_outputs"
            ],
            -profiles[name]["average_score"],
            profiles[name]["length_cutoffs"],
            profiles[name][
                "first_token_p95_s"
            ]
            if profiles[name][
                "first_token_p95_s"
            ] is not None
            else float("inf"),
        ),
    )

    return {
        "generated_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "profiles": profiles,
        "ranking": ranking,
        "winner": ranking[0] if ranking else None,
    }


def format_seconds(
    value: float | None,
) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def write_reports(
    *,
    output_dir: Path,
    results: list[TurnResult],
    summary: dict[str, Any],
) -> None:
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    leaderboard_lines = [
        "# NANCEE Unattended Tunable Benchmark",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Ranking is ordered by hard failures, hallucination flags, "
        "wrong-perspective output, quality score, length cutoffs, then p95 latency.",
        "",
        "| Rank | Profile | Description | Turns | Score | Hard fails | Hallucination flags | Length cutoffs | Incomplete | Recall zero hits | Perspective repairs | Wrong perspective output | First-token avg | First-token p95 | LLM avg |",
        "|---:|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for rank, profile_name in enumerate(
        summary["ranking"],
        start=1,
    ):
        row = summary["profiles"][profile_name]

        leaderboard_lines.append(
            "| "
            + " | ".join(
                (
                    str(rank),
                    profile_name,
                    row["description"],
                    str(row["turns"]),
                    f"{row['average_score']:.3f}",
                    str(row["hard_fails"]),
                    str(row["hallucination_flags"]),
                    str(row["length_cutoffs"]),
                    str(row["incomplete_responses"]),
                    str(row["zero_hit_recalls"]),
                    str(row["perspective_repairs"]),
                    str(
                        row[
                            "wrong_perspective_outputs"
                        ]
                    ),
                    format_seconds(
                        row[
                            "first_token_average_s"
                        ]
                    ),
                    format_seconds(
                        row["first_token_p95_s"]
                    ),
                    format_seconds(
                        row["llm_total_average_s"]
                    ),
                )
            )
            + " |"
        )

    winner = summary.get("winner")

    leaderboard_lines.extend(
        (
            "",
            f"## Automatic winner: {winner or 'none'}",
            "",
            "Do not accept a winner with hard failures. Review responses.md "
            "before adopting the tunables.",
            "",
            "## Profile values",
            "",
        )
    )

    for name in summary["ranking"]:
        profile = PROFILES[name]
        leaderboard_lines.extend(
            (
                f"### Profile {name} — {profile.description}",
                "",
                f"- normal: temperature={profile.normal_temperature:.2f}, "
                f"num_predict={profile.normal_num_predict}",
                f"- detailed: temperature={profile.detailed_temperature:.2f}, "
                f"num_predict={profile.detailed_num_predict}",
                f"- recall: temperature={profile.recall_temperature:.2f}, "
                f"num_predict={profile.recall_num_predict}",
                "- acknowledge: temperature=0.25, num_predict=18",
                "",
            )
        )

    flagged = [
        row
        for row in results
        if row.flags
    ]

    leaderboard_lines.extend(
        (
            "## Flag counts",
            "",
        )
    )

    flag_counts: dict[str, int] = {}

    for row in flagged:
        for flag in row.flags:
            flag_counts[flag] = (
                flag_counts.get(flag, 0)
                + 1
            )

    for flag, count in sorted(
        flag_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        leaderboard_lines.append(
            f"- {flag}: {count}"
        )

    (output_dir / "leaderboard.md").write_text(
        "\n".join(leaderboard_lines)
        + "\n",
        encoding="utf-8",
    )

    response_lines = [
        "# Responses for Human Review",
        "",
    ]

    for profile_name in summary["ranking"]:
        response_lines.extend(
            (
                f"## Profile {profile_name}",
                "",
            )
        )

        profile_rows = [
            row
            for row in results
            if row.profile == profile_name
        ]

        for row in profile_rows:
            response_lines.extend(
                (
                    f"### Round {row.round_index + 1} — {row.case_id}",
                    "",
                    f"**Prompt:** {row.prompt}",
                    "",
                    f"**Response:** {row.response}",
                    "",
                    f"Policy: `{row.policy}` · temp `{row.temperature:.2f}` · "
                    f"tokens `{row.num_predict}` · first token "
                    f"`{format_seconds(row.first_token_s)}s` · score "
                    f"`{row.score:.2f}` · hard fail `{row.hard_fail}`",
                    "",
                    "Flags: "
                    + (
                        ", ".join(row.flags)
                        if row.flags
                        else "none"
                    ),
                    "",
                )
            )

    (output_dir / "responses.md").write_text(
        "\n".join(response_lines)
        + "\n",
        encoding="utf-8",
    )


def run_profile_session(
    *,
    profile: Profile,
    round_index: int,
    output_dir: Path,
    results: list[TurnResult],
) -> None:
    recent = ShortTermMemory(
        max_turns=MEMORY_RECENT_PROMPT_TURNS,
    )

    archive = SessionArchive(
        max_turns=MEMORY_RECALL_TURN_LIMIT,
    )

    jsonl_path = output_dir / "turns.jsonl"
    csv_path = output_dir / "turns.csv"

    print(
        f"\n=== ROUND {round_index + 1} "
        f"PROFILE {profile.name}: "
        f"{profile.description} ===",
        flush=True,
    )

    for case_index, case in enumerate(
        CASES,
        start=1,
    ):
        started = time.perf_counter()

        try:
            result = run_case(
                profile=profile,
                round_index=round_index,
                case=case,
                recent=recent,
                archive=archive,
            )

        except Exception as error:
            result = TurnResult(
                timestamp=datetime.now().isoformat(
                    timespec="seconds"
                ),
                profile=profile.name,
                profile_description=profile.description,
                round_index=round_index,
                case_id=case.case_id,
                kind=case.kind,
                prompt=case.prompt_for_round(
                    round_index
                ),
                response="",
                policy="error",
                temperature=0.0,
                num_predict=0,
                first_token_s=None,
                llm_total_s=(
                    time.perf_counter()
                    - started
                ),
                prompt_eval_s=None,
                generation_s=None,
                response_tokens=None,
                done_reason="error",
                word_count=0,
                complete=False,
                retrieved_hits=0,
                retrieved_context_chars=0,
                stored=False,
                storage_skip_reason="",
                perspective_repaired=False,
                guard_action="error",
                score=0.0,
                hard_fail=True,
                flags=[
                    f"exception_{type(error).__name__}",
                    str(error),
                ],
                internal_log="",
            )

        results.append(result)
        write_jsonl(jsonl_path, result)
        append_csv(csv_path, result)

        print(
            f"[{profile.name} r{round_index + 1} "
            f"{case_index:02d}/{len(CASES)} "
            f"{case.case_id}] "
            f"score={result.score:.2f} "
            f"hard={result.hard_fail} "
            f"first={format_seconds(result.first_token_s)}s "
            f"answer={result.response!r}",
            flush=True,
        )

        if result.flags:
            print(
                "  flags="
                + ", ".join(result.flags),
                flush=True,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run NANCEE's current text/LLM/memory pipeline "
            "without ASR or TTS."
        )
    )

    parser.add_argument(
        "--minutes",
        type=float,
        default=110.0,
        help=(
            "Target runtime. The benchmark completes the current "
            "A/B/C/D round before stopping. Default: 110."
        ),
    )

    parser.add_argument(
        "--profiles",
        default="A,B,C,D",
        help="Comma-separated profile names. Default: A,B,C,D.",
    )

    parser.add_argument(
        "--rounds",
        type=int,
        default=0,
        help=(
            "Exact number of rounds. When greater than zero, "
            "overrides --minutes."
        ),
    )

    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional explicit result directory.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    selected_names = [
        name.strip().upper()
        for name in args.profiles.split(",")
        if name.strip()
    ]

    unknown = [
        name
        for name in selected_names
        if name not in PROFILES
    ]

    if unknown:
        raise SystemExit(
            f"Unknown profiles: {unknown}"
        )

    if not selected_names:
        raise SystemExit(
            "No profiles selected."
        )

    stamp = datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )

    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else (
            PROJECT_ROOT
            / "test"
            / "benchmark"
            / "results"
            / f"unattended_{stamp}"
        )
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest = {
        "started_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "project_root": str(PROJECT_ROOT),
        "model": LLM_MODEL,
        "target_minutes": args.minutes,
        "exact_rounds": args.rounds,
        "profiles": {
            name: asdict(PROFILES[name])
            for name in selected_names
        },
        "cases_per_profile": len(CASES),
    }

    (output_dir / "manifest.json").write_text(
        json.dumps(
            manifest,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "NANCEE UNATTENDED TEXT BENCHMARK",
        flush=True,
    )
    print(
        "No microphone, ASR, TTS, or sounddevice will start.",
        flush=True,
    )
    print(
        f"Project: {PROJECT_ROOT}",
        flush=True,
    )
    print(
        f"Model: {LLM_MODEL}",
        flush=True,
    )
    print(
        f"Results: {output_dir}",
        flush=True,
    )
    print(
        f"Profiles: {', '.join(selected_names)}",
        flush=True,
    )
    print(
        f"Cases per profile: {len(CASES)}",
        flush=True,
    )

    ensure_ollama_model_loaded(
        LLM_MODEL
    )

    call_supported(
        prime_ollama_context,
        history=[],
        memory_context="",
        retrieved_context="",
    )

    started = time.perf_counter()
    deadline = started + max(
        1.0,
        args.minutes * 60.0,
    )

    results: list[TurnResult] = []
    round_index = 0

    try:
        while True:
            # Rotate starting order to reduce profile-order bias.
            shift = round_index % len(selected_names)
            round_order = (
                selected_names[shift:]
                + selected_names[:shift]
            )

            for profile_name in round_order:
                run_profile_session(
                    profile=PROFILES[profile_name],
                    round_index=round_index,
                    output_dir=output_dir,
                    results=results,
                )

                summary = summarize(results)
                write_reports(
                    output_dir=output_dir,
                    results=results,
                    summary=summary,
                )

            round_index += 1

            if args.rounds > 0:
                if round_index >= args.rounds:
                    break
            elif time.perf_counter() >= deadline:
                break

    except KeyboardInterrupt:
        print(
            "\nBenchmark interrupted. Writing partial reports.",
            flush=True,
        )

    summary = summarize(results)
    write_reports(
        output_dir=output_dir,
        results=results,
        summary=summary,
    )

    elapsed = time.perf_counter() - started

    print(
        "\nBENCHMARK COMPLETE",
        flush=True,
    )
    print(
        f"Elapsed: {elapsed / 60.0:.1f} minutes",
        flush=True,
    )
    print(
        f"Turns: {len(results)}",
        flush=True,
    )
    print(
        f"Winner: {summary.get('winner')}",
        flush=True,
    )
    print(
        f"Leaderboard: {output_dir / 'leaderboard.md'}",
        flush=True,
    )
    print(
        f"Responses: {output_dir / 'responses.md'}",
        flush=True,
    )
    print(
        f"CSV: {output_dir / 'turns.csv'}",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
