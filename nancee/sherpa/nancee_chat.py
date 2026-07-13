import itertools
import json
import os
import queue
import re
import subprocess
import threading
import time
import urllib.error
from collections import deque
from pathlib import Path

import numpy as np
import sherpa_onnx
import sounddevice as sd
from config import (
    BLOCKSIZE,
    LATENCY_BRIDGE_ENABLED,
    LATENCY_BRIDGE_NORMAL_SECONDS,
    LATENCY_BRIDGE_PHRASES,
    LATENCY_BRIDGE_RECALL_SECONDS,
    LLM_MODEL,
    MEMORY_DEBUG_ENABLED,
    MEMORY_RECALL_CONTEXT_MAX_CHARACTERS,
    MEMORY_RECALL_ENABLED,
    MEMORY_RECALL_LIMIT,
    MEMORY_RECALL_MIN_SCORE,
    MEMORY_RECALL_SNIPPET_WORDS,
    MEMORY_RECALL_TURN_LIMIT,
    MEMORY_RECENT_PROMPT_TURNS,
    MODEL_DIR,
    NUM_THREADS,
    PREROLL_MS,
    SPEED,
    TTS_EMPHASIS_SPEED,
    TTS_FILLER_SPEED,
    TTS_GAP_FILLER_COOLDOWN_SECONDS,
    TTS_GAP_FILLER_ENABLED,
    TTS_GAP_FILLER_MAX_PER_TURN,
    TTS_GAP_FILLER_PHRASES,
    TTS_GAP_FILLER_SECONDS,
    TTS_MAX_NUM_SENTENCES,
    TTS_SILENCE_SCALE,
    USER_PROFILE_CONTEXT_MAX_CHARACTERS,
    USER_PROFILE_RETRIEVAL_ENABLED,
    USER_PROFILE_RETRIEVAL_LIMIT,
    VOICE_ID,
)
from authoritative_response import prepare_authoritative_response
from latency_bridge import LatencyBridge
from memory_policy import (
    is_complete_memory_statement,
    looks_like_personal_fact_fragment,
    memory_storage_skip_reason,
)
from profile_fact_index import ProfileFactIndex
from ollama_runtime import (
    ensure_ollama_model_loaded,
    prime_ollama_context,
    stream_ollama_response,
)
from recall_policy import (
    looks_like_perspective_correction,
    repair_recall_perspective,
)
from response_policy import select_response_policy
from session_archive import SessionArchive
from short_term_memory import ShortTermMemory
from tts_chunking import (
    extract_tts_chunk,
    is_filler_preface,
    is_punctuation_only,
)
from tts_request import build_tts_request
from user_profile import UserProfile

text_queue = queue.Queue()
stop_event = threading.Event()
audio_lock = threading.Lock()
audio_chunks = deque()
first_audio_enqueued = False

gap_filler_lock = threading.Lock()
gap_filler_audio_cycle = None
gap_fillers_used = 0
last_gap_filler_time = 0.0


NANCEE_ROOT = Path(__file__).resolve().parent.parent
ASR_DIRECTORY = NANCEE_ROOT / "asr"
ASR_PYTHON = ASR_DIRECTORY / "venv" / "bin" / "python"
ASR_WORKER_SCRIPT = ASR_DIRECTORY / "asr_worker.py"
asr_process = None


def memory_debug_enabled():
    return MEMORY_DEBUG_ENABLED


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
    r"\bwhere is\b",
    r"\bwhat do i\b",
    r"\bwhat i\s+(?:drive|own|have)\b",
    r"\bwhat am i driving\b",
    r"\bwhat car\s+(?:am i driving|do i drive|do i have)\b",
    r"\bwhat vehicle\s+(?:am i driving|do i drive|do i have)\b",
    r"\bwhat kind of\s+(?:car|vehicle)\s+do i\s+(?:drive|own|have)\b",
    r"\bwhat type of\s+(?:car|vehicle)\s+do i\s+(?:drive|own|have)\b",
    r"\bcan you tell me what i\s+(?:drive|own|have)\b",
    r"\bcan you tell me what car\s+(?:i drive|i have|i am driving)\b",
    r"\bcan you tell me what vehicle\s+(?:i drive|i have|i am driving)\b",
    r"\bwhat is my\b",
    r"\bwhat's my\b",
    r"\bwho is my\b",
    r"\bwho's my\b",
    r"\bwhere is .* from\b",
    r"\bwhere .* is from\b",
    r"\bwhat .* did i mention\b",
    r"\bwhat .* did i tell you\b",
    r"\bi told you .* earlier\b",
)

_DECLARATIVE_MEMORY_PATTERNS = (
    r"\bmy\s+[^?.!,]{1,60}\s+(?:is|are|was|were)\b",
    r"\bthis is\s+[a-z][a-z' -]{1,50}\b",
    r"\bi\s+(?:am|have|own|drive|like|prefer|use|work|live|need|want)\b",
    r"\bi[' ]?m\s+[a-z][a-z' -]{1,50}\b",
    r"\bwe\s+(?:are|have|own|use|work|live|need|want)\b",
    r"\bour\s+[^?.!,]{1,60}\s+(?:is|are|was|were)\b",
)


def normalize_user_text_for_memory(user_text):
    lowered = re.sub(
        r"\s+",
        " ",
        str(user_text).strip().lower(),
    )

    return re.sub(
        r"^(nancy|nancee)[,\s]+",
        "",
        lowered,
    )


def memory_sentence_chunks(user_text):
    text = normalize_user_text_for_memory(user_text)

    return [
        chunk.strip()
        for chunk in re.split(
            r"(?<=[.!?])\s+|[;\n]+",
            text,
        )
        if chunk.strip()
    ]


def looks_like_recall_request(user_text):
    lowered = normalize_user_text_for_memory(user_text)

    if not lowered:
        return False

    if looks_like_perspective_correction(lowered):
        return True

    return any(
        re.search(
            pattern,
            lowered,
            flags=re.IGNORECASE,
        )
        for pattern in _RECALL_QUERY_PATTERNS
    )


def looks_like_question_text(user_text):
    lowered = normalize_user_text_for_memory(user_text)

    if not lowered:
        return False

    if "?" in lowered:
        return True

    if lowered.startswith(_QUESTION_PREFIXES):
        return True

    return looks_like_recall_request(lowered)


def has_declarative_memory_content(user_text):
    for sentence in memory_sentence_chunks(user_text):
        if looks_like_question_text(sentence):
            continue

        if any(
            re.search(
                pattern,
                sentence,
                flags=re.IGNORECASE,
            )
            for pattern in _DECLARATIVE_MEMORY_PATTERNS
        ):
            return True

    return False


_MEMORY_JUNK_PATTERNS = (
    r"\bhere to test\b",
    r"\btest your memory\b",
    r"\btest .* capabilities\b",
    r"\bplease remember that\b",
    r"\bremember this\b",
)


def clean_memory_fragment(sentence):
    cleaned = str(sentence).strip()

    cleaned = re.sub(
        r"^[,\s.!?]+",
        "",
        cleaned,
    )

    cleaned = re.sub(
        r"^(hello|hi|hey|okay|ok|so|also|and|great|alright)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"^(nancy|nancee)[,\s]+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"^you know\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s+",
        " ",
        cleaned,
    ).strip()

    cleaned = cleaned.rstrip(".")

    # Convert "this is Anders" into a more useful memory fact.
    match = re.fullmatch(
        r"this is\s+([A-Z][A-Za-z' -]{1,50})",
        cleaned,
        flags=re.IGNORECASE,
    )

    if match:
        name = match.group(1).strip()
        return f"my name is {name}"

    return cleaned


def _clean_extracted_fact(value):
    cleaned = str(value).strip()

    cleaned = re.sub(
        r"^(hello|hi|hey|okay|ok|so|also|and|great|alright|nancy|nancee)[,\s]+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"^you know\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.split(
        r"\b(?:how are you|what about|can you|could you|would you|should you|please remember|remember that)\b",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    cleaned = cleaned.strip(" ,.!?")

    return re.sub(r"\s+", " ", cleaned).strip()


def extract_recall_user_text(user_text):
    text = normalize_user_text_for_memory(user_text)
    remembered = []

    fact_patterns = (
        (
            r"\bmy name is\s+([^?.!,]{1,60})",
            lambda match: f"the user name is {_clean_extracted_fact(match.group(1))}",
        ),
        (
            r"\bthis is\s+([^?.!,]{1,60})",
            lambda match: f"the user name is {_clean_extracted_fact(match.group(1))}",
        ),
        (
            r"\bi(?:'m| am)\s+(?!here\b|going\b|trying\b|testing\b|driving\b|heading\b|tired\b|hungry\b)([^?.!,]{1,40})",
            lambda match: f"the user name is {_clean_extracted_fact(match.group(1))}",
        ),
        (
            r"\bi drive\s+([^?.!,]{1,90})",
            lambda match: f"the user drives {_clean_extracted_fact(match.group(1))}",
        ),
        (
            r"\bi own\s+([^?.!,]{1,90})",
            lambda match: f"the user owns {_clean_extracted_fact(match.group(1))}",
        ),
        (
            r"\bmy (?:car|vehicle) is\s+([^?.!,]{1,90})",
            lambda match: (
                f"the user vehicle is {_clean_extracted_fact(match.group(1))}"
            ),
        ),
        (
            r"\bmy favorite band is\s+([^?.!,]{1,90})",
            lambda match: (
                f"the user favorite band is {_clean_extracted_fact(match.group(1))}"
            ),
        ),
        (
            r"\bmy mechanic(?:'s name)? is\s+([^?.!,]{1,60})",
            lambda match: (
                f"the user mechanic is {_clean_extracted_fact(match.group(1))}"
            ),
        ),
    )

    for pattern, builder in fact_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            fact = _clean_extracted_fact(builder(match))

            if fact:
                remembered.append(fact)

    if not remembered:
        return ""

    deduped = []
    seen = set()

    for fact in remembered:
        key = fact.lower()

        if key not in seen:
            seen.add(key)
            deduped.append(fact)

    return ". ".join(deduped).strip() + "."


def should_retrieve_recall(user_text):
    if has_declarative_memory_content(user_text):
        return False

    return looks_like_recall_request(user_text)


def should_store_recall_turn(user_text):
    if has_declarative_memory_content(user_text):
        return True

    if looks_like_question_text(user_text):
        return False

    return False


if MEMORY_RECALL_TURN_LIMIT <= 0:
    raise ValueError("MEMORY_RECALL_TURN_LIMIT must be positive.")

if MEMORY_RECENT_PROMPT_TURNS < 0:
    raise ValueError("MEMORY_RECENT_PROMPT_TURNS cannot be negative.")


def retrieve_session_context(recall_memory, user_text):
    started = time.perf_counter()

    if not MEMORY_RECALL_ENABLED:
        if memory_debug_enabled():
            print(
                f"[MEMORY RECALL] disabled=true query={user_text!r}",
                flush=True,
            )
        return ""

    retrieved_turns = recall_memory.retrieve(
        user_text,
        limit=MEMORY_RECALL_LIMIT,
        min_score=MEMORY_RECALL_MIN_SCORE,
        snippet_words=MEMORY_RECALL_SNIPPET_WORDS,
    )

    retrieved_context = recall_memory.format_related_context(
        retrieved_turns,
        max_characters=MEMORY_RECALL_CONTEXT_MAX_CHARACTERS,
    )

    elapsed = time.perf_counter() - started

    if memory_debug_enabled():
        print(
            "[MEMORY RECALL] "
            f"query={user_text!r} "
            f"hits={len(retrieved_turns)} "
            f"ids={[turn.get('archive_id', turn.get('id')) for turn in retrieved_turns]} "
            f"scores={[turn.get('score', turn.get('bm25_score')) for turn in retrieved_turns]} "
            f"context_characters={len(retrieved_context)} "
            f"elapsed={elapsed:.6f}s",
            flush=True,
        )

        if retrieved_context:
            print(
                f"[MEMORY RECALL CONTEXT]\n{retrieved_context}",
                flush=True,
            )
        else:
            print("[MEMORY RECALL CONTEXT] <none>", flush=True)

    return retrieved_context


def print_memory_status(recent_prompt_memory, recall_memory, phase):
    recent_stats = recent_prompt_memory.get_stats()
    recall_stats = recall_memory.get_stats()

    # Old SessionArchive used:
    #   turn_count, max_turns, archive_characters
    # New FTS5-backed store may use:
    #   count, max_memories
    recall_turns = recall_stats.get(
        "turn_count",
        recall_stats.get("count", 0),
    )

    recall_max = recall_stats.get(
        "max_turns",
        recall_stats.get("max_memories", 0),
    )

    recall_characters = recall_stats.get("archive_characters")

    if recall_characters is None:
        recall_characters = 0

        try:
            if hasattr(recall_memory, "store"):
                recall_characters = sum(
                    len(str(row.get("raw_text", "")))
                    for row in recall_memory.store.debug_dump()
                )
        except Exception:
            recall_characters = 0

    print(
        "[MEMORY STATUS] "
        f"phase={phase} "
        f"recent_turns={recent_stats['turn_count']} "
        f"recent_max={recent_stats['max_turns']} "
        f"recent_characters={recent_stats['history_characters']} "
        f"recall_turns={recall_turns} "
        f"recall_max={recall_max} "
        f"recall_characters={recall_characters}",
        flush=True,
    )


def read_asr_message():
    if asr_process is None or asr_process.stdout is None:
        raise RuntimeError("ASR worker is not running.")

    line = asr_process.stdout.readline()

    if not line:
        raise RuntimeError("ASR worker closed unexpectedly.")

    return json.loads(line)


def start_asr_worker():
    global asr_process

    if asr_process is not None and asr_process.poll() is None:
        return

    asr_process = subprocess.Popen(
        [
            str(ASR_PYTHON),
            str(ASR_WORKER_SCRIPT),
        ],
        cwd=str(ASR_DIRECTORY),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        # Let worker diagnostics appear directly in this terminal.
        stderr=None,
        text=True,
        bufsize=1,
    )

    message = read_asr_message()

    if message.get("type") != "ready":
        raise RuntimeError(f"ASR worker failed to start: {message}")


def send_asr_command(command):
    if asr_process is None or asr_process.stdin is None:
        raise RuntimeError("ASR worker is not running.")

    asr_process.stdin.write(command + "\n")

    asr_process.stdin.flush()


def get_spoken_user_input():
    start_asr_worker()

    input("\nPress Enter to begin speaking...")

    send_asr_command("START")

    message = read_asr_message()

    if message.get("type") != "started":
        print(
            f"[ASR ERROR] {message}",
            flush=True,
        )
        return ""

    input("Recording... Press Enter to stop.\n")

    send_asr_command("STOP")

    message = read_asr_message()

    if message.get("type") == "error":
        print(
            f"[ASR ERROR] {message.get('message')}",
            flush=True,
        )
        return ""

    if message.get("type") != "result":
        print(
            f"[ASR ERROR] Unexpected response: {message}",
            flush=True,
        )
        return ""

    print(
        f"[ASR] captured="
        f"{message.get('duration', 0.0):.2f}s "
        f"transcription="
        f"{message.get('transcription_seconds', 0.0):.2f}s "
        f"peak="
        f"{message.get('peak', 0.0):.4f}",
        flush=True,
    )

    return str(message.get("text", "")).strip()


def stop_asr_worker():
    global asr_process

    if asr_process is None:
        return

    if asr_process.poll() is None:
        try:
            send_asr_command("QUIT")
            asr_process.wait(timeout=3.0)

        except (
            BrokenPipeError,
            subprocess.TimeoutExpired,
        ):
            asr_process.terminate()

    asr_process = None


def build_tts():
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=f"{MODEL_DIR}/model.onnx",
                voices=f"{MODEL_DIR}/voices.bin",
                tokens=f"{MODEL_DIR}/tokens.txt",
                data_dir=f"{MODEL_DIR}/espeak-ng-data",
                lexicon=(f"{MODEL_DIR}/lexicon-us-en.txt,{MODEL_DIR}/lexicon-zh.txt"),
            ),
            provider="cpu",
            debug=False,
            num_threads=NUM_THREADS,
        ),
        max_num_sentences=TTS_MAX_NUM_SENTENCES,
    )

    if not config.validate():
        raise RuntimeError("Invalid Sherpa ONNX TTS config")

    return sherpa_onnx.OfflineTts(config)


def enqueue_audio(samples, sample_rate):
    global first_audio_enqueued

    samples = samples.astype(
        np.float32,
        copy=False,
    )

    with audio_lock:
        if not first_audio_enqueued and PREROLL_MS > 0:
            silence = np.zeros(
                int(sample_rate * (PREROLL_MS / 1000.0)),
                dtype=np.float32,
            )

            audio_chunks.append(silence)
            first_audio_enqueued = True

        audio_chunks.append(samples)


def output_callback(
    outdata,
    frames,
    stream_time,
    status,
):
    if status:
        print(
            f"\n[SOUNDDEVICE] {status}",
            flush=True,
        )

    outdata.fill(0)
    written = 0

    with audio_lock:
        while written < frames and audio_chunks:
            chunk = audio_chunks[0]
            remaining = frames - written

            if len(chunk) <= remaining:
                outdata[
                    written : written + len(chunk),
                    0,
                ] = chunk

                written += len(chunk)
                audio_chunks.popleft()

            else:
                outdata[written:, 0] = chunk[:remaining]
                audio_chunks[0] = chunk[remaining:]
                written = frames


def enqueue_tts_text(
    text,
    first_audio_callback=None,
    allow_gap_filler=False,
):
    request = build_tts_request(
        text=text,
        normal_speed=SPEED,
        emphasis_speed=TTS_EMPHASIS_SPEED,
        first_audio_callback=first_audio_callback,
        allow_gap_filler=allow_gap_filler,
    )

    if request is not None:
        text_queue.put(request)


def tts_worker(tts):
    gen_config = sherpa_onnx.GenerationConfig()
    gen_config.sid = VOICE_ID
    gen_config.silence_scale = TTS_SILENCE_SCALE

    while not stop_event.is_set() or not text_queue.empty():
        try:
            request = text_queue.get(
                timeout=0.05,
            )

        except queue.Empty:
            continue

        try:
            if request is None:
                continue

            text = request.text.strip()

            if not text:
                continue

            gen_config.speed = request.speed

            start = time.time()
            first_callback = None
            callback_count = 0
            gap_timer = None

            # Once set, a watchdog filler must never enqueue.
            real_audio_started = threading.Event()

            print(
                f"\n[TTS START] {text!r} "
                f"speed={request.speed:.2f} "
                f"emphasis={request.emphasized}",
                flush=True,
            )

            def callback(
                samples: np.ndarray,
                progress: float,
            ):
                nonlocal first_callback
                nonlocal callback_count
                nonlocal gap_timer

                callback_count += 1
                now = time.time()

                first_audio_for_request = first_callback is None

                if first_audio_for_request:
                    # Mark real audio first so a timer callback
                    # already waking up cannot enqueue a filler.
                    real_audio_started.set()

                    if gap_timer is not None:
                        gap_timer.cancel()
                        gap_timer = None

                    first_callback = now

                    print(
                        f"[TTS FIRST AUDIO] "
                        f"{first_callback - start:.3f}s | "
                        f"progress={progress:.3f} | "
                        f"speed={request.speed:.2f} | "
                        f"{text!r}",
                        flush=True,
                    )

                enqueue_audio(
                    samples,
                    tts.sample_rate,
                )

                if first_audio_for_request and request.first_audio_callback is not None:
                    request.first_audio_callback()

                return 1

            if TTS_GAP_FILLER_ENABLED and request.allow_gap_filler:

                def play_gap_filler():
                    global gap_fillers_used
                    global last_gap_filler_time

                    # Real audio may have arrived while this timer
                    # thread was waking up.
                    if real_audio_started.is_set():
                        return

                    with audio_lock:
                        answer_audio_waiting = bool(
                            audio_chunks
                        )

                    if answer_audio_waiting:
                        return

                    with gap_filler_lock:
                        # Check again after acquiring the shared
                        # filler-state lock.
                        if real_audio_started.is_set():
                            return

                        if (
                            gap_fillers_used
                            >= TTS_GAP_FILLER_MAX_PER_TURN
                        ):
                            return

                        if gap_filler_audio_cycle is None:
                            return

                        now = time.monotonic()

                        if (
                            last_gap_filler_time > 0.0
                            and (
                                now
                                - last_gap_filler_time
                            )
                            < TTS_GAP_FILLER_COOLDOWN_SECONDS
                        ):
                            if memory_debug_enabled():
                                remaining = (
                                    TTS_GAP_FILLER_COOLDOWN_SECONDS
                                    - (
                                        now
                                        - last_gap_filler_time
                                    )
                                )

                                print(
                                    "\n[TTS GAP FILLER SKIP] "
                                    "cooldown_active=true "
                                    f"remaining={remaining:.3f}s",
                                    flush=True,
                                )

                            return

                        (
                            phrase,
                            filler_samples,
                            filler_sample_rate,
                        ) = next(
                            gap_filler_audio_cycle
                        )

                        # One final race check before consuming the
                        # budget and placing filler audio in the queue.
                        if real_audio_started.is_set():
                            return

                        gap_fillers_used += 1
                        last_gap_filler_time = now
                        count = gap_fillers_used

                        print(
                            "\n[TTS GAP FILLER] "
                            f"phrase={phrase!r} "
                            f"count={count}",
                            flush=True,
                        )

                        enqueue_audio(
                            filler_samples.copy(),
                            filler_sample_rate,
                        )

                gap_timer = threading.Timer(
                    TTS_GAP_FILLER_SECONDS,
                    play_gap_filler,
                )

                gap_timer.daemon = True
                gap_timer.start()

            try:
                audio = tts.generate(
                    text,
                    gen_config,
                    callback=callback,
                )

            finally:
                if gap_timer is not None:
                    gap_timer.cancel()
                    gap_timer = None

            # Some Sherpa configurations return complete audio
            # without invoking the streaming callback.
            if callback_count == 0:
                real_audio_started.set()

                enqueue_audio(
                    np.asarray(
                        audio.samples,
                        dtype=np.float32,
                    ),
                    audio.sample_rate,
                )

                if request.first_audio_callback is not None:
                    request.first_audio_callback()

            elapsed = time.time() - start
            duration = len(audio.samples) / audio.sample_rate

            rtf = elapsed / duration if duration else 999

            print(
                f"[TTS DONE] "
                f"elapsed={elapsed:.3f}s "
                f"duration={duration:.3f}s "
                f"RTF={rtf:.3f} "
                f"speed={request.speed:.2f}",
                flush=True,
            )

        except Exception as error:
            print(
                f"[TTS ERROR] {error!r}",
                flush=True,
            )

        finally:
            text_queue.task_done()


def stream_text_to_tts(text_iter, first_audio_callback=None):
    buffer = ""
    full_response = []
    is_first = True
    first_token_time = None
    pending_fillers = []
    start = time.time()
    pending_first_audio_callback = first_audio_callback

    def queue_meaningful_chunk(
        chunk,
        opening_chunk,
    ):
        nonlocal pending_fillers
        nonlocal pending_first_audio_callback

        cleaned_chunk = chunk.strip()
        cleaned_chunk = re.sub(
            r"^[.!?,;:]+\s*",
            "",
            cleaned_chunk,
        )

        if not cleaned_chunk:
            return

        if is_punctuation_only(cleaned_chunk):
            return

        # Speak the first generated phrase immediately.
        if opening_chunk:
            enqueue_tts_text(
                cleaned_chunk,
                first_audio_callback=pending_first_audio_callback,
            )
            pending_first_audio_callback = None
            return

        # Hold filler-only fragments that appear later so the
        # response cannot end awkwardly on a filler.
        if is_filler_preface(cleaned_chunk):
            pending_fillers.append(cleaned_chunk)
            return

        if pending_fillers:
            enqueue_tts_text(" ".join(pending_fillers))
            pending_fillers = []

        # Later chunks may use a short pre-generated filler
        # if Kokoro leaves a noticeable silent gap.
        enqueue_tts_text(
            cleaned_chunk,
            allow_gap_filler=True,
        )

    for token in text_iter:
        full_response.append(token)

        if first_token_time is None:
            first_token_time = time.time()

            print(
                f"\n[LLM FIRST TOKEN] {first_token_time - start:.3f}s\n",
                flush=True,
            )

        print(
            token,
            end="",
            flush=True,
        )

        buffer += token

        while True:
            extracted = extract_tts_chunk(
                buffer,
                is_first,
            )

            if extracted is None:
                break

            chunk, buffer = extracted

            print(
                f"\n[TEXT -> TTS] {chunk!r}",
                flush=True,
            )

            queue_meaningful_chunk(
                chunk,
                opening_chunk=is_first,
            )

            is_first = False

    final = buffer.strip()

    if final and not is_punctuation_only(final):
        print()

        print(
            f"[TEXT -> TTS FINAL] {final!r}",
            flush=True,
        )

        queue_meaningful_chunk(
            final,
            opening_chunk=is_first,
        )

    full_text = "".join(full_response).strip()

    if pending_fillers:
        print(
            "[TTS SKIP] "
            "Dropped trailing filler-only text: "
            f"{' '.join(pending_fillers)!r}",
            flush=True,
        )

    if is_filler_preface(full_text):
        return ""

    return full_text


def generate_bridge_audio(
    tts,
    phrase,
    speed=TTS_FILLER_SPEED,
):
    """Generate bridge speech once before the conversation loop."""
    request = build_tts_request(
        text=phrase,
        normal_speed=SPEED,
        emphasis_speed=TTS_EMPHASIS_SPEED,
    )

    if request is None:
        raise ValueError("Latency bridge phrase produced an empty TTS request.")

    gen_config = sherpa_onnx.GenerationConfig()
    gen_config.sid = VOICE_ID
    gen_config.silence_scale = TTS_SILENCE_SCALE
    gen_config.speed = speed

    audio = tts.generate(
        phrase,
        gen_config,
    )

    samples = np.asarray(
        audio.samples,
        dtype=np.float32,
    ).copy()

    return (
        samples,
        int(audio.sample_rate),
    )


def collect_text_response(text_iter):
    """Collect a short recall answer so it can be checked before speech."""
    started = time.time()
    first_token_seen = False
    tokens = []

    for token in text_iter:
        if not first_token_seen:
            first_token_seen = True
            print(
                f"\n[LLM FIRST TOKEN] {time.time() - started:.3f}s\n",
                flush=True,
            )

        print(token, end="", flush=True)
        tokens.append(token)

    if tokens:
        print()

    return "".join(tokens).strip()


def enqueue_complete_response(
    text,
    first_audio_callback=None,
):
    """Chunk a validated complete response through existing TTS rules."""
    buffer = str(text).strip()
    is_first = True
    pending_first_audio_callback = first_audio_callback

    while buffer:
        extracted = extract_tts_chunk(
            buffer,
            is_first,
        )

        if extracted is None:
            enqueue_tts_text(
                buffer,
                first_audio_callback=pending_first_audio_callback,
            )
            break

        chunk, buffer = extracted

        enqueue_tts_text(
            chunk,
            first_audio_callback=pending_first_audio_callback,
            allow_gap_filler=not is_first,
        )

        pending_first_audio_callback = None
        is_first = False


def wait_for_audio_to_drain():
    while True:
        with audio_lock:
            remaining = len(audio_chunks)

        if remaining == 0:
            break

        time.sleep(0.05)

    time.sleep(0.25)


# NANCEE FTS5 ONLY MEMORY MODE START
#
# Temporary test mode:
# - Store raw non-question user utterances.
# - Retrieve from FTS5 for any question.
# - Do not extract facts.
# - Do not use aliases.
# - Do not use regex fact memory.
#
# Question detection is intentionally broad because FTS5 should decide
# whether anything useful exists.
def extract_recall_user_text(user_text):
    return ""


def has_declarative_memory_content(user_text):
    return is_complete_memory_statement(user_text)


def should_store_recall_turn(user_text):
    return is_complete_memory_statement(user_text)


def should_retrieve_recall(user_text):
    return (
        looks_like_question_text(user_text)
        or looks_like_personal_fact_fragment(user_text)
    )


# NANCEE FTS5 ONLY MEMORY MODE END


def main():
    print(
        "Loading Sherpa Kokoro...",
        flush=True,
    )

    tts = build_tts()
    bridge_audio_options = [
        (
            phrase,
            *generate_bridge_audio(
                tts,
                phrase,
            ),
        )
        for phrase in LATENCY_BRIDGE_PHRASES
    ]

    bridge_audio_cycle = itertools.cycle(bridge_audio_options)

    global gap_filler_audio_cycle

    gap_filler_audio_options = [
        (
            phrase,
            *generate_bridge_audio(
                tts,
                phrase,
            ),
        )
        for phrase in TTS_GAP_FILLER_PHRASES
    ]

    gap_filler_audio_cycle = itertools.cycle(gap_filler_audio_options)

    print(
        "[LATENCY BRIDGE] "
        f"enabled={LATENCY_BRIDGE_ENABLED} "
        f"normal_threshold={LATENCY_BRIDGE_NORMAL_SECONDS:.3f}s "
        f"recall_threshold={LATENCY_BRIDGE_RECALL_SECONDS:.3f}s",
        flush=True,
    )

    print(
        f"Loaded. sample_rate={tts.sample_rate} "
        f"threads={NUM_THREADS} "
        f"voice_id={VOICE_ID}",
        flush=True,
    )

    worker = threading.Thread(
        target=tts_worker,
        args=(tts,),
        name="SherpaTTSWorker",
        daemon=True,
    )

    worker.start()

    try:
        ensure_ollama_model_loaded(
            LLM_MODEL,
        )

        prime_ollama_context(
            history=[],
            memory_context="",
        )

    except RuntimeError as error:
        print(
            f"[STARTUP ERROR] {error}",
            flush=True,
        )

        stop_event.set()
        worker.join(timeout=2.0)

        raise SystemExit(1)

    recent_prompt_memory = ShortTermMemory(
        max_turns=MEMORY_RECENT_PROMPT_TURNS,
    )

    recall_memory = SessionArchive(
        max_turns=MEMORY_RECALL_TURN_LIMIT,
    )

    user_profile = UserProfile.load()
    profile_index = ProfileFactIndex(
        user_profile.facts,
    )

    print(
        "[USER PROFILE INDEX] "
        f"loaded={not user_profile.is_empty()} "
        f"facts={profile_index.count()}",
        flush=True,
    )

    print(
        "Opening persistent audio stream...",
        flush=True,
    )

    with sd.OutputStream(
        channels=1,
        samplerate=tts.sample_rate,
        dtype="float32",
        blocksize=BLOCKSIZE,
        callback=output_callback,
    ):
        while True:
            try:
                user_text = get_spoken_user_input()

            except KeyboardInterrupt:
                print(
                    "\nStopping.",
                    flush=True,
                )
                break

            if not user_text:
                continue

            if is_punctuation_only(user_text):
                print(
                    "[ASR] Ignoring punctuation-only transcription.",
                    flush=True,
                )
                continue

            if len(user_text) > 1000:
                print(
                    "[ASR] Ignoring implausibly long transcription.",
                    flush=True,
                )
                continue

            print(
                f"\nYou: {user_text}",
                flush=True,
            )

            if user_text.lower() in {
                "q",
                "quit",
                "exit",
            }:
                break

            global_start = time.time()

            global gap_fillers_used
            global last_gap_filler_time

            with gap_filler_lock:
                gap_fillers_used = 0
                last_gap_filler_time = 0.0

            personal_fact_fragment = (
                looks_like_personal_fact_fragment(user_text)
            )
            recall_requested = should_retrieve_recall(user_text)
            explicit_recall_requested = (
                looks_like_recall_request(user_text)
                or personal_fact_fragment
            )

            profile_started = time.perf_counter()
            effective_profile_context = ""
            profile_hits = []

            if USER_PROFILE_RETRIEVAL_ENABLED:
                (
                    effective_profile_context,
                    profile_hits,
                ) = profile_index.retrieve_context(
                    user_text,
                    limit=USER_PROFILE_RETRIEVAL_LIMIT,
                    max_characters=(
                        USER_PROFILE_CONTEXT_MAX_CHARACTERS
                    ),
                )

            profile_context_found = bool(
                effective_profile_context.strip()
            )
            profile_elapsed = (
                time.perf_counter()
                - profile_started
            )

            if memory_debug_enabled():
                print(
                    "[USER PROFILE RETRIEVAL] "
                    f"hits={[hit.key for hit in profile_hits]} "
                    f"context_characters="
                    f"{len(effective_profile_context)} "
                    f"elapsed={profile_elapsed:.6f}s",
                    flush=True,
                )

            if profile_context_found:
                # A matching profile fact is confirmed and authoritative.
                # Do not add a weaker raw-session FTS5 hit to the same prompt.
                retrieved_context = ""
                memory_context_found = False

                if memory_debug_enabled():
                    print(
                        "[MEMORY RECALL] skipped=true "
                        "reason=authoritative_profile_hit",
                        flush=True,
                    )

            elif recall_requested:
                retrieved_context = retrieve_session_context(
                    recall_memory,
                    user_text,
                )

                memory_context_found = bool(
                    str(retrieved_context).strip()
                )

            else:
                retrieved_context = ""
                memory_context_found = False

                if memory_debug_enabled():
                    print(
                        "[MEMORY RECALL] skipped=true "
                        "reason=not_recall_request",
                        flush=True,
                    )

            if (
                explicit_recall_requested
                and not memory_context_found
                and not profile_context_found
            ):
                # Keep a recall miss inside the LLM personality path,
                # but give the model a tiny authoritative instruction
                # instead of the complete user profile.
                effective_profile_context = (
                    "No matching confirmed fact about the human user "
                    "was retrieved. Say only that you do not remember "
                    "it yet."
                )

                if memory_debug_enabled():
                    print(
                        "[USER FACT MISS] llm_answer=true",
                        flush=True,
                    )

            authoritative_context_found = (
                memory_context_found
                or bool(effective_profile_context.strip())
            )

            response_policy = select_response_policy(
                user_text,
                authoritative_context_found=(
                    authoritative_context_found
                ),
            )

            print(
                "[RESPONSE POLICY] "
                f"name={response_policy.name} "
                f"temperature={response_policy.temperature:.2f} "
                f"num_predict={response_policy.num_predict} "
                f"drop_history={response_policy.drop_history}",
                flush=True,
            )

            print_memory_status(
                recent_prompt_memory,
                recall_memory,
                "before_request",
            )

            print(
                "\nNancee: ",
                end="",
                flush=True,
            )
            bridge = None

            (
                bridge_phrase,
                bridge_samples,
                bridge_sample_rate,
            ) = next(bridge_audio_cycle)

            def play_latency_bridge():
                print(
                    f"\n[LATENCY BRIDGE] fired phrase={bridge_phrase!r}",
                    flush=True,
                )

                enqueue_audio(
                    bridge_samples.copy(),
                    bridge_sample_rate,
                )

            try:
                if authoritative_context_found:
                    bridge_delay_seconds = LATENCY_BRIDGE_RECALL_SECONDS
                else:
                    bridge_delay_seconds = LATENCY_BRIDGE_NORMAL_SECONDS

                bridge = LatencyBridge(
                    delay_seconds=bridge_delay_seconds,
                    enabled=LATENCY_BRIDGE_ENABLED,
                    on_fire=play_latency_bridge,
                )

                bridge.start()

                if looks_like_perspective_correction(user_text):
                    request_history = recent_prompt_memory.get_messages()
                elif (
                    authoritative_context_found
                    or response_policy.drop_history
                ):
                    # Retrieved facts are authoritative. Dropping the
                    # one-turn chat history keeps the prompt smaller and
                    # prevents a prior verbose answer from contaminating
                    # the fact-based response.
                    request_history = []
                else:
                    request_history = recent_prompt_memory.get_messages()

                response = stream_ollama_response(
                    user_text=user_text,
                    history=request_history,
                    memory_context=effective_profile_context,
                    retrieved_context=retrieved_context,
                    response_instruction=(
                        response_policy.instruction
                    ),
                    temperature=response_policy.temperature,
                    num_predict=response_policy.num_predict,
                )

                if authoritative_context_found:
                    # Fact-backed answers are collected before speech so a
                    # small-model contradiction cannot enter TTS or history.
                    assistant_text = collect_text_response(
                        response,
                    )

                    if memory_context_found:
                        assistant_text, repaired = (
                            repair_recall_perspective(
                                assistant_text,
                            )
                        )

                        if repaired:
                            print(
                                "[MEMORY PERSPECTIVE REPAIR] "
                                f"output={assistant_text!r}",
                                flush=True,
                            )

                    fact_miss = (
                        explicit_recall_requested
                        and not memory_context_found
                        and not profile_context_found
                    )

                    assistant_text, guard_action = (
                        prepare_authoritative_response(
                            assistant_text,
                            profile_hits=profile_hits,
                            fact_miss=fact_miss,
                        )
                    )

                    if memory_debug_enabled():
                        print(
                            "[AUTHORITATIVE RESPONSE GUARD] "
                            f"action={guard_action} "
                            f"output={assistant_text!r}",
                            flush=True,
                        )

                    enqueue_complete_response(
                        assistant_text,
                        first_audio_callback=bridge.resolve,
                    )
                else:
                    assistant_text = stream_text_to_tts(
                        response,
                        first_audio_callback=bridge.resolve,
                    )

            except (
                TimeoutError,
                urllib.error.URLError,
                urllib.error.HTTPError,
                RuntimeError,
            ) as error:
                print(
                    f"\n[OLLAMA ERROR] {error}",
                    flush=True,
                )

                text_queue.join()
                wait_for_audio_to_drain()
                continue

            finally:
                if bridge is not None:
                    bridge.resolve()

            if not assistant_text:
                print(
                    "\n[LLM ERROR] Ollama returned no response text.",
                    flush=True,
                )
                continue

            # Preserve Nancee's real answer in the one-turn live prompt.
            # FTS5 still stores only the raw user utterance.
            memory_assistant_text = assistant_text

            # FTS5 raw utterance recall archive.
            # Store only complete user statements. Questions, commands,
            # fragments, and likely ASR debris are deliberately rejected.
            if should_store_recall_turn(user_text):
                added_memory_id = recall_memory.add_turn(
                    user_text=user_text,
                    assistant_text=memory_assistant_text,
                )

                if memory_debug_enabled():
                    if added_memory_id is not None:
                        print(
                            f"[MEMORY RAW ADD] id={added_memory_id} "
                            f"stored={user_text!r}",
                            flush=True,
                        )
                    else:
                        print(
                            "[MEMORY RAW SKIP] "
                            "backend_rejected=true",
                            flush=True,
                        )
            elif memory_debug_enabled():
                print(
                    "[MEMORY RAW SKIP] "
                    f"reason={memory_storage_skip_reason(user_text)} "
                    f"text={user_text!r}",
                    flush=True,
                )

            recent_prompt_memory.add_turn(
                user_text=user_text,
                assistant_text=memory_assistant_text,
            )

            text_queue.join()
            wait_for_audio_to_drain()

            print_memory_status(
                recent_prompt_memory,
                recall_memory,
                "after_turn",
            )

            if memory_debug_enabled():
                print(
                    "[MEMORY DEBUG] "
                    f"recent={recent_prompt_memory.get_stats()} "
                    f"recall={recall_memory.get_stats()}",
                    flush=True,
                )

            total = time.time() - global_start

            print(
                f"\n[TURN DONE] total={total:.3f}s",
                flush=True,
            )

        stop_asr_worker()

        stop_event.set()
        worker.join(timeout=2.0)

        print(
            "Done.",
            flush=True,
        )


if __name__ == "__main__":
    main()
