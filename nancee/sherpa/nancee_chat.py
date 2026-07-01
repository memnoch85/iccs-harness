import json
import os
import queue
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
    LLM_MODEL,
    MAX_CHUNK_WORDS,
    MEMORY_CONSOLIDATE_CHARACTERS,
    MEMORY_CONSOLIDATE_TURNS,
    MEMORY_KEEP_RECENT_TURNS,
    MODEL_DIR,
    NUM_THREADS,
    PREROLL_MS,
    SPEED,
    TTS_MAX_NUM_SENTENCES,
    TTS_SILENCE_SCALE,
    VOICE_ID,
)
from memory_consolidator import consolidate_memory
from ollama_runtime import (
    ensure_ollama_model_loaded,
    stream_ollama_response,
)
from short_term_memory import ShortTermMemory

text_queue = queue.Queue()
stop_event = threading.Event()
audio_lock = threading.Lock()
audio_chunks = deque()
first_audio_enqueued = False

NANCEE_ROOT = Path(__file__).resolve().parent.parent
ASR_DIRECTORY = NANCEE_ROOT / "asr"
ASR_PYTHON = ASR_DIRECTORY / "venv" / "bin" / "python"
ASR_WORKER_SCRIPT = ASR_DIRECTORY / "asr_worker.py"
asr_process = None


def evaluate_memory_consolidation(memory):
    should_consolidate = memory.should_consolidate(
        max_active_turns=MEMORY_CONSOLIDATE_TURNS,
        max_history_characters=MEMORY_CONSOLIDATE_CHARACTERS,
    )

    if not should_consolidate:
        return False

    batch = memory.get_consolidation_batch(
        keep_recent_turns=MEMORY_KEEP_RECENT_TURNS,
    )

    if not batch:
        return False

    before_stats = memory.get_stats()

    print(
        "\n[MEMORY CONSOLIDATION] "
        f"active_turns={before_stats['turn_count']} "
        f"history_chars={before_stats['history_characters']} "
        f"consolidating={len(batch)} "
        f"keeping={MEMORY_KEEP_RECENT_TURNS}",
        flush=True,
    )

    started = time.time()

    try:
        new_summary = consolidate_memory(
            existing_summary=memory.get_session_summary(),
            turns=batch,
        )

    except RuntimeError as error:
        print(
            f"[MEMORY CONSOLIDATION ERROR] {error}. Original turns were preserved.",
            flush=True,
        )
        return False

    memory.apply_consolidation(
        new_summary=new_summary,
        consolidated_turn_count=len(batch),
    )

    elapsed = time.time() - started
    after_stats = memory.get_stats()

    print(
        "[MEMORY CONSOLIDATION DONE] "
        f"elapsed={elapsed:.3f}s "
        f"active_turns={after_stats['turn_count']} "
        f"summary_chars={after_stats['summary_characters']} "
        f"consolidations={after_stats['consolidation_count']}",
        flush=True,
    )

    if (
        os.getenv(
            "NANCEE_MEMORY_DEBUG",
            "false",
        ).lower()
        == "true"
    ):
        print(
            f"[MEMORY SUMMARY] {memory.get_session_summary()}",
            flush=True,
        )

    return True


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


def tts_worker(tts):
    gen_config = sherpa_onnx.GenerationConfig()
    gen_config.sid = VOICE_ID
    gen_config.speed = SPEED
    gen_config.silence_scale = TTS_SILENCE_SCALE

    while not stop_event.is_set() or not text_queue.empty():
        try:
            text = text_queue.get(
                timeout=0.05,
            )
        except queue.Empty:
            continue

        text = text.strip()

        if not text:
            text_queue.task_done()
            continue

        start = time.time()
        first_callback = None
        callback_count = 0

        print(
            f"\n[TTS START] {text!r}",
            flush=True,
        )

        def callback(
            samples: np.ndarray,
            progress: float,
        ):
            nonlocal first_callback
            nonlocal callback_count

            callback_count += 1
            now = time.time()

            if first_callback is None:
                first_callback = now

                print(
                    f"[TTS FIRST AUDIO] "
                    f"{first_callback - start:.3f}s | "
                    f"progress={progress:.3f} | "
                    f"{text!r}",
                    flush=True,
                )

            enqueue_audio(
                samples,
                tts.sample_rate,
            )

            return 1

        audio = tts.generate(
            text,
            gen_config,
            callback=callback,
        )

        if callback_count == 0:
            enqueue_audio(
                audio.samples,
                audio.sample_rate,
            )

        elapsed = time.time() - start
        duration = len(audio.samples) / audio.sample_rate

        rtf = elapsed / duration if duration else 999

        print(
            f"[TTS DONE] elapsed={elapsed:.3f}s duration={duration:.3f}s RTF={rtf:.3f}",
            flush=True,
        )

        text_queue.task_done()


def is_punctuation_only(text):
    stripped = text.strip()

    return bool(stripped) and not any(character.isalnum() for character in stripped)


def has_sentence_break(text):
    return text.strip().endswith(
        (
            ".",
            "!",
            "?",
            ",",
            ";",
            ":",
            "\n",
        )
    )


def word_count(text):
    return len(text.strip().split())


def should_emit(buffer, is_first):
    stripped = buffer.strip()

    if not stripped:
        return False

    if is_punctuation_only(stripped):
        return False

    words = word_count(stripped)

    # Best case: emit at natural punctuation.
    if has_sentence_break(stripped):
        if is_first:
            return words >= 1

        return words >= 3

    # If the raw buffer does not end with whitespace,
    # the current streamed token may end in the middle
    # of a word.
    if buffer and not buffer[-1].isspace():
        return False

    # First chunks can only be forced at a clean
    # word boundary.
    if is_first:
        return words >= MAX_CHUNK_WORDS

    # Later chunks can also be forced, but only at a
    # clean word boundary.
    return words >= MAX_CHUNK_WORDS


def stream_text_to_tts(text_iter):
    buffer = ""
    full_response = []
    is_first = True
    first_token_time = None
    start = time.time()

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
        stripped = buffer.strip()

        if not stripped:
            continue

        # Never send punctuation alone.
        if is_punctuation_only(stripped):
            continue

        if should_emit(
            buffer,
            is_first,
        ):
            chunk = stripped

            print(
                f"\n[TEXT -> TTS] {chunk!r}",
                flush=True,
            )

            text_queue.put(chunk)

            buffer = ""
            is_first = False

    final = buffer.strip()

    if final and not is_punctuation_only(final):
        print()

        print(
            f"[TEXT -> TTS FINAL] {final!r}",
            flush=True,
        )

        text_queue.put(final)
    return "".join(full_response).strip()


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

    except RuntimeError as error:
        print(
            f"[STARTUP ERROR] {error}",
            flush=True,
        )

        stop_event.set()
        worker.join(timeout=2.0)

        raise SystemExit(1)

    short_term_memory = ShortTermMemory(
        max_turns=None,
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

            print(
                "\nNancee: ",
                end="",
                flush=True,
            )

            try:
                response = stream_ollama_response(
                    user_text=user_text,
                    history=short_term_memory.get_messages(),
                    memory_context=short_term_memory.build_memory_context(),
                )

                assistant_text = stream_text_to_tts(response)
                if assistant_text:
                    short_term_memory.add_turn(
                        user_text=user_text,
                        assistant_text=assistant_text,
                    )
                else:
                    print(
                        "\n[LLM ERROR] Ollama returned no response text.",
                        flush=True,
                    )

                if os.getenv("NANCEE_MEMORY_DEBUG", "false").lower() == "true":
                    print(f"[MEMORY DEBUG] {short_term_memory.get_stats()}")

            except urllib.error.URLError as error:
                print(
                    f"\n[OLLAMA ERROR] {error}",
                    flush=True,
                )
                continue

            text_queue.join()
            wait_for_audio_to_drain()

            total = time.time() - global_start

            print(
                f"\n[TURN DONE] total={total:.3f}s",
                flush=True,
            )

            evaluate_memory_consolidation(
                short_term_memory,
            )


if __name__ == "__main__":
    main()
