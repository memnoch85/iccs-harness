import os
import json
import time
import queue
import threading
import urllib.request
import urllib.error
from collections import deque
import numpy as np
import sounddevice as sd
import sherpa_onnx


MODEL_DIR = os.environ.get("SHERPA_MODEL_DIR", "kokoro-multi-lang-v1_0")

OLLAMA_URL = os.environ.get(
    "OLLAMA_URL",
    "http://localhost:11434/api/chat",
).strip()

LLM_MODEL = os.environ.get("LLM_MODEL", "llama3.2:3b")

VOICE_ID = int(os.environ.get("VOICE_ID", "3"))   # 3 = af_heart
SPEED = float(os.environ.get("SPEED", "1.2"))

NUM_THREADS = int(os.environ.get("SHERPA_THREADS", "4"))

BLOCKSIZE = int(os.environ.get("BLOCKSIZE", "1024"))
PREROLL_MS = int(os.environ.get("PREROLL_MS", "0"))

FIRST_CHUNK_MIN_WORDS = int(os.environ.get("FIRST_CHUNK_MIN_WORDS", "1"))
TARGET_CHUNK_WORDS = int(os.environ.get("TARGET_CHUNK_WORDS", "5"))
MAX_CHUNK_WORDS = int(os.environ.get("MAX_CHUNK_WORDS", "8"))


text_queue = queue.Queue()
stop_event = threading.Event()

audio_lock = threading.Lock()
audio_chunks = deque()

first_audio_enqueued = False


def build_tts():
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=f"{MODEL_DIR}/model.onnx",
                voices=f"{MODEL_DIR}/voices.bin",
                tokens=f"{MODEL_DIR}/tokens.txt",
                data_dir=f"{MODEL_DIR}/espeak-ng-data",
                lexicon=f"{MODEL_DIR}/lexicon-us-en.txt,{MODEL_DIR}/lexicon-zh.txt",
            ),
            provider="cpu",
            debug=False,
            num_threads=NUM_THREADS,
        ),
        max_num_sentences=1,
    )

    if not config.validate():
        raise RuntimeError("Invalid Sherpa ONNX TTS config")

    return sherpa_onnx.OfflineTts(config)


def enqueue_audio(samples, sample_rate):
    global first_audio_enqueued

    samples = samples.astype(np.float32, copy=False)

    with audio_lock:
        if not first_audio_enqueued and PREROLL_MS > 0:
            silence = np.zeros(
                int(sample_rate * (PREROLL_MS / 1000.0)),
                dtype=np.float32,
            )
            audio_chunks.append(silence)
            first_audio_enqueued = True

        audio_chunks.append(samples)


def output_callback(outdata, frames, stream_time, status):
    if status:
        print(f"\n[SOUNDDEVICE] {status}", flush=True)

    outdata.fill(0)
    written = 0

    with audio_lock:
        while written < frames and audio_chunks:
            chunk = audio_chunks[0]
            remaining = frames - written

            if len(chunk) <= remaining:
                outdata[written:written + len(chunk), 0] = chunk
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
    gen_config.silence_scale = 0.2

    while not stop_event.is_set() or not text_queue.empty():
        try:
            text = text_queue.get(timeout=0.05)
        except queue.Empty:
            continue

        text = text.strip()
        if not text:
            text_queue.task_done()
            continue

        start = time.time()
        first_callback = None
        callback_count = 0

        print(f"\n[TTS START] {text!r}", flush=True)

        def callback(samples: np.ndarray, progress: float):
            nonlocal first_callback
            nonlocal callback_count

            callback_count += 1
            now = time.time()

            if first_callback is None:
                first_callback = now
                print(
                    f"[TTS FIRST AUDIO] {first_callback - start:.3f}s | "
                    f"progress={progress:.3f} | {text!r}",
                    flush=True,
                )

            enqueue_audio(samples, tts.sample_rate)
            return 1

        audio = tts.generate(text, gen_config, callback=callback)

        if callback_count == 0:
            enqueue_audio(audio.samples, audio.sample_rate)

        elapsed = time.time() - start
        duration = len(audio.samples) / audio.sample_rate
        rtf = elapsed / duration if duration else 999

        print(
            f"[TTS DONE] elapsed={elapsed:.3f}s "
            f"duration={duration:.3f}s "
            f"RTF={rtf:.3f}",
            flush=True,
        )

        text_queue.task_done()


def is_punctuation_only(text):
    stripped = text.strip()
    return bool(stripped) and not any(ch.isalnum() for ch in stripped)


def has_sentence_break(text):
    return text.strip().endswith((".", "!", "?", ",", ";", ":", "\n"))


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

    # Critical streaming-token rule:
    # If the raw buffer does not end with whitespace, we may be in the middle
    # of a streamed subword like "mountain" + "ous".
    #
    # Do NOT force emit from MAX_CHUNK_WORDS unless the current token ended
    # cleanly at a word boundary.
    if buffer and not buffer[-1].isspace():
        return False

    # First chunk can be forced only at a clean word boundary.
    if is_first:
        return words >= MAX_CHUNK_WORDS

    # Later chunks can also be forced, but only at a clean word boundary.
    return words >= MAX_CHUNK_WORDS


def stream_text_to_tts(text_iter):
    buffer = ""
    is_first = True
    first_token_time = None
    start = time.time()

    for token in text_iter:
        if first_token_time is None:
            first_token_time = time.time()
            print(
                f"\n[LLM FIRST TOKEN] {first_token_time - start:.3f}s\n",
                flush=True,
            )

        print(token, end="", flush=True)
        buffer += token

        stripped = buffer.strip()

        if not stripped:
            continue

        # Never send punctuation alone.
        if is_punctuation_only(stripped):
            continue

        if should_emit(buffer, is_first):
            chunk = stripped

            print(f"\n[TEXT -> TTS] {chunk!r}", flush=True)
            text_queue.put(chunk)

            buffer = ""
            is_first = False

    # Final flush.
    final = buffer.strip()

    if final and not is_punctuation_only(final):
        print()
        print(f"[TEXT -> TTS FINAL] {final!r}", flush=True)
        text_queue.put(final)


def stream_ollama_response(user_text):
    system_prompt = (
        "You are Nancee, a warm, witty, sarcastic in-car software  companion and automotive assistant. "
        "Do not invent personal experiences or vehicle conditions unless the user gives them or tools report them. "
        "Sound like a smart passenger, not a chatbot and not a roleplay character. "
        "Start each response with one short spoken filler followed by punctuation, like 'So,' 'Umm,' 'Well,' 'Actually,' or 'Alright,'. "
        "After the filler, immediately answer the user with a complete thought. "
        "For greetings and casual conversation, reply in 1 to 2 complete spoken sentences. "
        "For explanations or stories, give complete thoughts, but stay under 120 words unless asked for detail. "
        "Use natural punctuation. "
        "Do not output standalone punctuation. "
        "Do not write role labels like User: or Nancee:. "
        "Do not prefix your answer with your name. "
        "Ask at most one follow-up question. "
    )

    payload = {
        "model": LLM_MODEL,
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_text,
            },
        ],
        "options": {
            "temperature": 0.6,
            "num_thread": 4,
            "num_predict": 130,
        },
    }

    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue

            data = json.loads(line)

            if data.get("done"):
                break

            token = data.get("message", {}).get("content", "")
            if token:
                yield token



def wait_for_audio_to_drain():
    while True:
        with audio_lock:
            remaining = len(audio_chunks)

        if remaining == 0:
            break

        time.sleep(0.05)

    time.sleep(0.25)


if __name__ == "__main__":
    print("Loading Sherpa Kokoro...", flush=True)
    tts = build_tts()
    print(
        f"Loaded. sample_rate={tts.sample_rate} "
        f"threads={NUM_THREADS} voice_id={VOICE_ID}",
        flush=True,
    )

    worker = threading.Thread(
        target=tts_worker,
        args=(tts,),
        name="SherpaTTSWorker",
        daemon=True,
    )
    worker.start()

    print("Opening persistent audio stream...", flush=True)

    with sd.OutputStream(
        channels=1,
        samplerate=tts.sample_rate,
        dtype="float32",
        blocksize=BLOCKSIZE,
        callback=output_callback,
    ):
        while True:
            try:
                user_text = input("\nYou: ").strip()
            except KeyboardInterrupt:
                print("\nStopping.", flush=True)
                break

            if not user_text:
                continue

            if user_text.lower() in {"q", "quit", "exit"}:
                break

            global_start = time.time()

            print("\nNancee: ", end="", flush=True)

            try:
                stream_text_to_tts(stream_ollama_response(user_text))
            except urllib.error.URLError as e:
                print(f"\n[OLLAMA ERROR] {e}", flush=True)
                continue

            text_queue.join()
            wait_for_audio_to_drain()

            total = time.time() - global_start
            print(f"\n[TURN DONE] total={total:.3f}s", flush=True)

    stop_event.set()
    worker.join(timeout=2.0)

    print("Done.", flush=True)
