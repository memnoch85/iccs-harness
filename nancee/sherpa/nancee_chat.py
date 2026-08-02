import itertools
import json
import queue
import random
import re
import subprocess
import threading
import time
import urllib.error
from collections import deque
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import numpy as np
import sherpa_onnx
import sounddevice as sd
from authoritative_response import prepare_authoritative_response
from config import (
    BLOCKSIZE,
    LATENCY_BRIDGE_ENABLED,
    LATENCY_BRIDGE_GREETING_PHRASES,
    LATENCY_BRIDGE_GREETING_SECONDS,
    LATENCY_BRIDGE_NORMAL_SECONDS,
    LATENCY_BRIDGE_PHRASES,
    LATENCY_BRIDGE_RECALL_SECONDS,
    LLM_MODEL,
    MEMORY_DEBUG_ENABLED,
    MEMORY_RECALL_CONTEXT_MAX_CHARACTERS,
    MEMORY_RECALL_ENABLED,
    MEMORY_RECALL_LIMIT,
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
    TTS_GREETING_BRIDGE_SPEED,
    TTS_MAX_NUM_SENTENCES,
    TTS_SILENCE_SCALE,
    VOICE_ID,
)
from directive_perspective import repair_directive_perspective
from generation_completion import (
    final_fragment_is_safe,
    prepare_clarification_response,
    trim_incomplete_length_tail,
    trim_prompt_role_leak,
)
from input_router import route_user_input
from latency_bridge import (
    LatencyBridge,
    calculate_remaining_bridge_delay,
)
from memory_policy import memory_storage_skip_reason
from ollama_runtime import (
    create_ollama_iccs,
    ensure_ollama_model_loaded,
)
from recall_policy import repair_recall_perspective
from response_policy import response_policy_for_route
from session_archive import SessionArchive
from session_memory_store import filter_memory_hits_by_overlap
from short_term_memory import ShortTermMemory
from tts_chunking import (
    extract_tts_chunk,
    is_filler_preface,
    is_punctuation_only,
)
from tts_request import build_tts_request

#global fields
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


@dataclass(frozen=True)
class SpokenUserInput:
    text: str
    stopped_at: float | None


def retrieve_session_context(recall_memory, user_text, allow_weak_match=False):
    # Timing
    started = time.perf_counter()

    # Recall disabled
    if not MEMORY_RECALL_ENABLED:
        if MEMORY_DEBUG_ENABLED:
            print(
                f"[MEMORY RECALL] disabled=true query={user_text!r}",
                flush=True,
            )

        return ""

    # Retrieve and filter memory
    retrieved_turns = recall_memory.retrieve(user_text, limit=MEMORY_RECALL_LIMIT)
    unfiltered_count = len(retrieved_turns)
    retrieved_turns = filter_memory_hits_by_overlap(user_text, retrieved_turns, minimum_overlap=2, allow_weak_match=allow_weak_match)

    # Report filtered memory
    if MEMORY_DEBUG_ENABLED and len(retrieved_turns) != unfiltered_count:
        print(
            "[MEMORY RECALL FILTER] "
            f"removed={unfiltered_count - len(retrieved_turns)} "
            "reason=weak_overlap minimum=2",
            flush=True,
        )

    # Format retrieved context
    retrieved_context = recall_memory.format_related_context(retrieved_turns, max_characters=MEMORY_RECALL_CONTEXT_MAX_CHARACTERS)
    elapsed = time.perf_counter() - started

    # Report recall results
    if MEMORY_DEBUG_ENABLED:
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

    # FTS5-backed store may use:
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
        except Exception:  # noqa: BLE001
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


def play_asr_ready_tone(sample_rate):
    """Play a clear two-tone cue through Nancee's active output stream."""
    sample_rate = int(sample_rate)

    def make_tone(frequency_hz, duration_seconds):
        sample_count = int(
            sample_rate * duration_seconds
        )

        positions = (
            np.arange(
                sample_count,
                dtype=np.float32,
            )
            / float(sample_rate)
        )

        samples = (
            0.35
            * np.sin(
                2.0
                * np.pi
                * frequency_hz
                * positions
            )
        ).astype(
            np.float32,
            copy=False,
        )

        fade_count = min(
            int(sample_rate * 0.015),
            sample_count // 2,
        )

        if fade_count > 0:
            fade = np.linspace(
                0.0,
                1.0,
                fade_count,
                dtype=np.float32,
            )

            samples[:fade_count] *= fade
            samples[-fade_count:] *= fade[::-1]

        return samples

    gap = np.zeros(
        int(sample_rate * 0.07),
        dtype=np.float32,
    )

    cue = np.concatenate(
        (
            make_tone(750.0, 0.18),
            gap,
            make_tone(1050.0, 0.18),
        )
    )

    print(
        "[ASR READY TONE] playing=true "
        f"duration={len(cue) / sample_rate:.3f}s",
        flush=True,
    )

    enqueue_audio(
        cue,
        sample_rate,
    )

    wait_for_audio_to_drain()


def get_spoken_user_input(
    output_sample_rate,
):
    start_asr_worker()

    input("\nPress Enter to begin speaking...")

    send_asr_command("START")

    message = read_asr_message()

    if message.get("type") != "started":
        print(
            f"[ASR ERROR] {message}",
            flush=True,
        )
        return SpokenUserInput("", None)

    # The microphone is confirmed active. Play the cue,
    # then discard anything recorded while the cue played.
    play_asr_ready_tone(
        output_sample_rate,
    )

    send_asr_command("CLEAR")

    message = read_asr_message()

    if message.get("type") != "cleared":
        print(
            f"[ASR ERROR] Could not clear cue audio: {message}",
            flush=True,
        )
        return SpokenUserInput("", None)

    print(
        "[ASR READY TONE] microphone_buffer_cleared=true",
        flush=True,
    )

    input("Recording... Press Enter to stop.\n")

    stop_requested_at = time.perf_counter()

    print(
        "[LATENCY CLOCK] "
        "event=recording_stop "
        f"timestamp={stop_requested_at:.6f}",
        flush=True,
    )
    print(
        "[ASR] recording_stopped=true transcribing=true",
        flush=True,
    )

    send_asr_command("STOP")

    message = read_asr_message()
    stop_to_result_seconds = time.perf_counter() - stop_requested_at

    if message.get("type") == "error":
        print(
            f"[ASR ERROR] {message.get('message')}",
            flush=True,
        )
        return SpokenUserInput("", stop_requested_at)

    if message.get("type") != "result":
        print(
            f"[ASR ERROR] Unexpected response: {message}",
            flush=True,
        )
        return SpokenUserInput("", stop_requested_at)

    print(
        f"[ASR] captured="
        f"{message.get('duration', 0.0):.2f}s "
        f"transcription="
        f"{message.get('transcription_seconds', 0.0):.2f}s "
        f"stop_to_result={stop_to_result_seconds:.2f}s "
        f"peak="
        f"{message.get('peak', 0.0):.4f}",
        flush=True,
    )

    return SpokenUserInput(
        str(message.get("text", "")).strip(),
        stop_requested_at,
    )


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


def fire_route_latency_bridge(
    *,
    stopped_at,
    deadline,
    phase,
    phrase,
    samples,
    sample_rate,
    target_seconds,
):
    fired_at = time.perf_counter()
    elapsed_since_stop = fired_at - stopped_at
    deadline_error = fired_at - deadline

    print(
        "\n[LATENCY BRIDGE FIRE] "
        f"phase={phase} "
        f"phrase={phrase!r} "
        f"fired_at={fired_at:.6f} "
        f"elapsed_since_stop={elapsed_since_stop:.3f}s "
        f"target={target_seconds:.3f}s "
        f"deadline_error={deadline_error:+.3f}s",
        flush=True,
    )

    enqueue_audio(
        samples.copy(),
        sample_rate,
    )


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
                real_audio_started=real_audio_started,
                request=request,
                start=start,
                text=text,
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

                if (
                    first_audio_for_request
                    and request.first_audio_callback is not None
                ):
                    request.first_audio_callback()

                enqueue_audio(
                    samples,
                    tts.sample_rate,
                )

                return 1

            if TTS_GAP_FILLER_ENABLED and request.allow_gap_filler:

                def play_gap_filler(
                    _real_audio_started=real_audio_started,
                ):
                    global gap_fillers_used
                    global last_gap_filler_time

                    # Real audio may have arrived while this timer
                    # thread was waking up.
                    if _real_audio_started.is_set():
                        return

                    with audio_lock:
                        answer_audio_waiting = bool(audio_chunks)

                    if answer_audio_waiting:
                        return

                    with gap_filler_lock:
                        # Check again after acquiring the shared
                        # filler-state lock.
                        if _real_audio_started.is_set():
                            return

                        if gap_fillers_used >= TTS_GAP_FILLER_MAX_PER_TURN:
                            return

                        if gap_filler_audio_cycle is None:
                            return

                        now = time.monotonic()

                        if (
                            last_gap_filler_time > 0.0
                            and (now - last_gap_filler_time)
                            < TTS_GAP_FILLER_COOLDOWN_SECONDS
                        ):
                            if MEMORY_DEBUG_ENABLED:
                                remaining = TTS_GAP_FILLER_COOLDOWN_SECONDS - (
                                    now - last_gap_filler_time
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
                        ) = next(gap_filler_audio_cycle)

                        # One final race check before consuming the
                        # budget and placing filler audio in the queue.
                        if _real_audio_started.is_set():
                            return

                        gap_fillers_used += 1
                        last_gap_filler_time = now
                        count = gap_fillers_used

                        print(
                            f"\n[TTS GAP FILLER] phrase={phrase!r} count={count}",
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

                if request.first_audio_callback is not None:
                    request.first_audio_callback()

                enqueue_audio(
                    np.asarray(
                        audio.samples,
                        dtype=np.float32,
                    ),
                    audio.sample_rate,
                )

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

        except Exception as error:  # noqa: BLE001
            print(
                f"[TTS ERROR] {error!r}",
                flush=True,
            )

        finally:
            text_queue.task_done()


def stream_text_to_tts(
    text_iter,
    first_audio_callback=None,
    completion_state=None,
):
    buffer = ""
    full_response = []
    is_first = True
    first_token_time = None
    pending_fillers = []
    start = time.time()
    pending_first_audio_callback = first_audio_callback
    prompt_role_leak_stopped = False

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

        if prompt_role_leak_stopped:
            continue

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
        buffer, role_leak_found = trim_prompt_role_leak(buffer)

        if role_leak_found:
            prompt_role_leak_stopped = True
            print(
                "\n[LLM STREAM GUARD] stopped=true reason=prompt_role_leak",
                flush=True,
            )

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
        if final_fragment_is_safe(
            final,
            completion_state,
        ):
            print()

            print(
                f"[TEXT -> TTS FINAL] {final!r}",
                flush=True,
            )

            queue_meaningful_chunk(
                final,
                opening_chunk=is_first,
            )
        else:
            print(
                f"\n[TTS SKIP] Dropped incomplete token-limit tail: {final!r}",
                flush=True,
            )

    full_text = "".join(full_response).strip()
    full_text, history_role_leak_trimmed = trim_prompt_role_leak(
        full_text,
    )

    if history_role_leak_trimmed:
        print(
            "[LLM STREAM GUARD] Removed prompt-role continuation from recent history.",
            flush=True,
        )

    full_text, history_tail_trimmed = trim_incomplete_length_tail(
        full_text,
        completion_state,
    )

    if history_tail_trimmed:
        print(
            "[LLM COMPLETION GUARD] "
            "Removed incomplete token-limit tail "
            "from recent history.",
            flush=True,
        )

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

    # Shuffle once at startup, then use every phrase before repeating.
    random.shuffle(bridge_audio_options)

    bridge_audio_cycle = itertools.cycle(
        bridge_audio_options
    )

    greeting_bridge_audio_options = [
        (
            phrase,
            *generate_bridge_audio(
                tts,
                phrase,
                speed=TTS_GREETING_BRIDGE_SPEED,
            ),
        )
        for phrase in LATENCY_BRIDGE_GREETING_PHRASES
    ]

    # Shuffle once per startup, then cycle through all phrases.
    random.shuffle(greeting_bridge_audio_options)

    greeting_bridge_audio_cycle = itertools.cycle(
        greeting_bridge_audio_options
    )
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
        f"greeting_threshold="
        f"{LATENCY_BRIDGE_GREETING_SECONDS:.3f}s "
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

    iccs = create_ollama_iccs()

    try:
        ensure_ollama_model_loaded(
            LLM_MODEL,
        )

        iccs.prime_startup(
            history=[],
            memory_context="",
            reason="startup",
        )

    except RuntimeError as error:
        print(
            f"[STARTUP ERROR] {error}",
            flush=True,
        )

        iccs.close()
        stop_event.set()
        worker.join(timeout=2.0)

        raise SystemExit(1)

    recent_prompt_memory = ShortTermMemory(
        max_turns=MEMORY_RECENT_PROMPT_TURNS,
    )

    recall_memory = SessionArchive(
        max_turns=MEMORY_RECALL_TURN_LIMIT,
    )

    print(
        "Opening persistent audio stream...",
        flush=True,
    )

    try:
        with sd.OutputStream(
            channels=1,
            samplerate=tts.sample_rate,
            dtype="float32",
            blocksize=BLOCKSIZE,
            callback=output_callback,
        ):
            while True:
                try:
                    spoken_input = get_spoken_user_input(
                        tts.sample_rate,
                    )
                    user_text = spoken_input.text
                    recording_stopped_at = spoken_input.stopped_at
                    bridge = None

                except KeyboardInterrupt:
                    print(
                        "\nStopping.",
                        flush=True,
                    )
                    break

                if recording_stopped_at is None:
                    if bridge is not None:
                        bridge.resolve()

                    print(
                        "[LATENCY CLOCK] "
                        "event=recording_stop_missing "
                        "route_bridge_skipped=true",
                        flush=True,
                    )
                    continue

                previous_turns = recent_prompt_memory.get_turns_snapshot()
                previous_turn = previous_turns[-1] if previous_turns else None

                input_route = route_user_input(
                    user_text,
                    previous_turn=previous_turn,
                )

                if input_route.kind == "invalid":
                    if bridge is not None:
                        bridge.resolve()

                    print(
                        "[INPUT ROUTE] "
                        f"kind=invalid reason={input_route.reason}",
                        flush=True,
                    )
                    continue

                print(
                    f"\nYou: {user_text}",
                    flush=True,
                )

                print(
                    "[INPUT ROUTE] "
                    f"kind={input_route.kind} "
                    f"reason={input_route.reason} "
                    f"retrieve_recall={input_route.retrieve_recall} "
                    f"explicit_recall={input_route.explicit_recall} "
                    f"allow_weak_match={input_route.allow_weak_match} "
                    f"store_recall={input_route.store_recall}",
                    flush=True,
                )

                if input_route.kind == "exit":
                    if bridge is not None:
                        bridge.resolve()
                    break

                global_start = time.time()

                global gap_fillers_used
                global last_gap_filler_time

                with gap_filler_lock:
                    gap_fillers_used = 0
                    last_gap_filler_time = 0.0

                recall_requested = input_route.retrieve_recall
                explicit_recall_requested = input_route.explicit_recall

                if recall_requested:
                    retrieved_context = retrieve_session_context(
                        recall_memory,
                        user_text,
                        allow_weak_match=input_route.allow_weak_match,
                    )
                    memory_context_found = bool(
                        str(retrieved_context).strip()
                    )
                else:
                    retrieved_context = ""
                    memory_context_found = False

                    if MEMORY_DEBUG_ENABLED:
                        print(
                            "[MEMORY RECALL] "
                            "skipped=true reason=not_recall_request",
                            flush=True,
                        )

                fact_miss = (
                    explicit_recall_requested
                    and not memory_context_found
                )

                request_memory_context = ""

                if fact_miss:
                    request_memory_context = (
                        "No matching confirmed fact about the human user "
                        "was retrieved. Say only that you do not remember "
                        "it yet."
                    )

                    if MEMORY_DEBUG_ENABLED:
                        print(
                            "[USER FACT MISS] llm_answer=true",
                            flush=True,
                        )

                authoritative_context_found = (
                    input_route.explicit_recall
                    and memory_context_found
                )

                authoritative_response_required = (
                    authoritative_context_found
                    or fact_miss
                )

                response_policy = response_policy_for_route(
                    input_route.kind,
                    authoritative_context_found=authoritative_context_found,
                    fact_miss=fact_miss,
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
                if response_policy.name == "greeting":
                    selected_bridge_audio_cycle = greeting_bridge_audio_cycle
                else:
                    selected_bridge_audio_cycle = bridge_audio_cycle

                (
                    bridge_phrase,
                    bridge_samples,
                    bridge_sample_rate,
                ) = next(selected_bridge_audio_cycle)

                try:
                    if response_policy.name == "greeting":
                        bridge_target_seconds = LATENCY_BRIDGE_GREETING_SECONDS
                    elif authoritative_response_required:
                        bridge_target_seconds = LATENCY_BRIDGE_RECALL_SECONDS
                    else:
                        bridge_target_seconds = LATENCY_BRIDGE_NORMAL_SECONDS

                    (
                        bridge_delay_seconds,
                        bridge_elapsed_seconds,
                    ) = calculate_remaining_bridge_delay(
                        bridge_target_seconds,
                        started_at=recording_stopped_at,
                    )
                    logical_deadline = (
                        recording_stopped_at
                        + bridge_target_seconds
                    )

                    route_decided_at = time.perf_counter()

                    print(
                        "[LATENCY BRIDGE CLOCK] "
                        f"phase={response_policy.name} "
                        f"logical_start={recording_stopped_at:.6f} "
                        f"route_decided_at={route_decided_at:.6f} "
                        f"elapsed_since_stop={bridge_elapsed_seconds:.3f}s "
                        f"target={bridge_target_seconds:.3f}s "
                        f"remaining={bridge_delay_seconds:.3f}s "
                        f"logical_deadline={logical_deadline:.6f}",
                        flush=True,
                    )

                    print(
                        "[LATENCY BRIDGE DEADLINE] phase=route "
                        f"target={bridge_target_seconds:.3f}s "
                        f"elapsed_since_stop={bridge_elapsed_seconds:.3f}s "
                        f"remaining={bridge_delay_seconds:.3f}s",
                        flush=True,
                    )


                    route_bridge_callback = partial(
                        fire_route_latency_bridge,
                        stopped_at=recording_stopped_at,
                        deadline=logical_deadline,
                        phase=response_policy.name,
                        phrase=bridge_phrase,
                        samples=bridge_samples,
                        sample_rate=bridge_sample_rate,
                        target_seconds=bridge_target_seconds,
                    )

                    bridge = LatencyBridge(
                        delay_seconds=bridge_delay_seconds,
                        enabled=LATENCY_BRIDGE_ENABLED,
                        on_fire=route_bridge_callback,
                    )

                    physical_arm_at = time.perf_counter()

                    print(
                        "[LATENCY BRIDGE ARM] "
                        f"phase={response_policy.name} "
                        f"logical_start={recording_stopped_at:.6f} "
                        f"physical_arm={physical_arm_at:.6f} "
                        f"elapsed_before_arm="
                        f"{physical_arm_at - recording_stopped_at:.3f}s "
                        f"delay_given={bridge_delay_seconds:.3f}s "
                        f"logical_deadline={logical_deadline:.6f}",
                        flush=True,
                    )

                    bridge.start()

                    if input_route.force_keep_history:
                        request_history = recent_prompt_memory.get_messages()
                    elif authoritative_response_required or response_policy.drop_history:
                        # Explicit fact answers and explicit misses are isolated
                        # from conversational history. Background enrichment for
                        # an ordinary question keeps the live one-turn history.
                        request_history = []
                    else:
                        request_history = recent_prompt_memory.get_messages()

                    live_history = recent_prompt_memory.get_messages()
                    require_exact_iccs_prefix = (
                        request_history == live_history
                    )

                    completion_state = {}
                    assistant_text = ""
                    response = None

                    response = iccs.respond(
                        user_text=user_text,
                        history=request_history,
                        memory_context=request_memory_context,
                        require_exact_prefix=require_exact_iccs_prefix,
                        retrieved_context=retrieved_context,
                        response_instruction=response_policy.instruction,
                        temperature=response_policy.temperature,
                        num_predict=response_policy.num_predict,
                        completion_state=completion_state,
                    )

                    if response is None:
                        raise RuntimeError(
                            "Ollama response stream was not created."
                        )

                    elif authoritative_response_required:
                        # Fact-backed answers are collected before speech so a
                        # small-model contradiction cannot enter TTS or history.
                        assistant_text = collect_text_response(
                            response,
                        )
                        assistant_text, authoritative_role_leak_trimmed = (
                            trim_prompt_role_leak(assistant_text)
                        )

                        if authoritative_role_leak_trimmed:
                            print(
                                "[LLM STREAM GUARD] "
                                "Removed prompt-role continuation "
                                "before authoritative validation.",
                                flush=True,
                            )

                        assistant_text, authoritative_tail_trimmed = (
                            trim_incomplete_length_tail(
                                assistant_text,
                                completion_state,
                            )
                        )

                        if authoritative_tail_trimmed:
                            print(
                                "[LLM COMPLETION GUARD] "
                                "Removed incomplete token-limit tail "
                                "before authoritative validation.",
                                flush=True,
                            )

                        if not assistant_text:
                            assistant_text = (
                                "I don't remember that clearly enough."
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

                        assistant_text, guard_action = (
                            prepare_authoritative_response(
                                assistant_text,
                                fact_miss=fact_miss,
                                retrieved_context=retrieved_context,
                            )
                        )

                        if MEMORY_DEBUG_ENABLED:
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

                    elif response_policy.name == "directive":
                        collected_directive = collect_text_response(
                            response,
                        )

                        (
                            assistant_text,
                            directive_role_leak_trimmed,
                        ) = trim_prompt_role_leak(
                            collected_directive,
                        )

                        if directive_role_leak_trimmed:
                            print(
                                "[DIRECTIVE RESPONSE GUARD] "
                                "action=role_leak_trimmed",
                                flush=True,
                            )

                        assistant_text, directive_tail_trimmed = (
                            trim_incomplete_length_tail(
                                assistant_text,
                                completion_state,
                            )
                        )

                        if directive_tail_trimmed:
                            print(
                                "[DIRECTIVE RESPONSE GUARD] "
                                "action=length_tail_trimmed",
                                flush=True,
                            )

                        if not assistant_text:
                            assistant_text = "Could you repeat that?"

                        assistant_text, directive_repaired = (
                            repair_directive_perspective(
                                user_text,
                                assistant_text,
                            )
                        )

                        if directive_repaired:
                            print(
                                "[DIRECTIVE PERSPECTIVE REPAIR] "
                                f"output={assistant_text!r}",
                                flush=True,
                            )

                        enqueue_complete_response(
                            assistant_text,
                            first_audio_callback=bridge.resolve,
                        )

                    elif response_policy.name == "clarify":
                        collected_clarification = collect_text_response(
                            response,
                        )
                        assistant_text, clarify_guard_action = (
                            prepare_clarification_response(
                                collected_clarification,
                                completion_state,
                            )
                        )

                        print(
                            "[CLARIFY RESPONSE GUARD] "
                            f"action={clarify_guard_action} "
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
                            completion_state=completion_state,
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

                    iccs.prime_next(
                        history=recent_prompt_memory.get_messages(),
                        memory_context="",
                        reason="request_recovery",
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

                    iccs.prime_next(
                        history=recent_prompt_memory.get_messages(),
                        memory_context="",
                        reason="empty_response_recovery",
                    )
                    continue

                # Preserve Nancee's real answer in the one-turn live prompt.
                # FTS5 still stores only the raw user utterance.
                memory_assistant_text = assistant_text

                # Apply narrow "it was NEW, not OLD" corrections using the
                # single router decision. Rewriting the original sentence
                # preserves its action words for later FTS5 recall.
                correction = input_route.correction
                corrected_memory_id = None

                if correction is not None:
                    new_value, old_value = correction
                    corrected_memory_id = recall_memory.apply_simple_correction(
                        new_value=new_value,
                        old_value=old_value,
                    )

                    if MEMORY_DEBUG_ENABLED:
                        print(
                            "[MEMORY RAW CORRECT] "
                            f"id={corrected_memory_id} "
                            f"new={new_value!r} "
                            f"old={old_value!r}",
                            flush=True,
                        )

                # FTS5 recall storage is also controlled by the router. A short
                # contextual answer such as "I sure did" may carry a resolved
                # statement built from Nancee's previous question.
                if corrected_memory_id is not None:
                    pass
                elif input_route.store_recall:
                    recall_storage_text = (
                        input_route.recall_storage_text
                        or user_text
                    )

                    added_memory_id = recall_memory.add_turn(
                        user_text=recall_storage_text,
                    )

                    if MEMORY_DEBUG_ENABLED:
                        if added_memory_id is not None:
                            print(
                                f"[MEMORY RAW ADD] id={added_memory_id} "
                                f"stored={recall_storage_text!r} "
                                f"source={user_text!r}",
                                flush=True,
                            )
                        else:
                            print(
                                "[MEMORY RAW SKIP] backend_rejected=true",
                                flush=True,
                            )
                elif MEMORY_DEBUG_ENABLED:
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

                # Direct speaker responses bypass iccs.respond(), so the
                # previous turn's background prime may still be registered even
                # after its worker has finished. Consume that result before
                # scheduling the new completed-turn prefix. For ordinary LLM
                # turns this is a no-op because respond() already waited.
                iccs.wait_for_prepared_prefix()

                iccs.prime_next(
                    history=recent_prompt_memory.get_messages(),
                    memory_context="",
                    reason="completed_turn",
                )

                wait_for_audio_to_drain()

                print_memory_status(
                    recent_prompt_memory,
                    recall_memory,
                    "after_turn",
                )

                if MEMORY_DEBUG_ENABLED:
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

    finally:
        try:
            iccs.close()
        except RuntimeError as error:
            print(
                f"[ICCS SHUTDOWN ERROR] {error}",
                flush=True,
            )
        finally:
            stop_asr_worker()
            stop_event.set()
            worker.join(timeout=2.0)

    print(
        "Done.",
        flush=True,
    )



if __name__ == "__main__":
    main()
