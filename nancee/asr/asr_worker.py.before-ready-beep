#!/usr/bin/env python3

from __future__ import annotations

import os

# NANCEE runs Whisper from the local HF cache.
# Do not contact Hugging Face Hub during startup.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


import json
import sys
import time
from contextlib import redirect_stdout
from typing import Optional

import numpy as np
import sounddevice as sd
from transformers.utils import logging as transformers_logging

from transcribe import (
    DEFAULT_MODEL,
    DEFAULT_SAMPLE_RATE,
    WhisperTranscriber,
)


class PersistentRecorder:
    """Microphone recorder controlled through START and STOP commands."""

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> None:
        self.sample_rate = sample_rate
        self.audio_blocks: list[np.ndarray] = []
        self.stream: Optional[sd.InputStream] = None

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ) -> None:
        del frames
        del time_info

        if status:
            print(
                f"[ASR AUDIO WARNING] {status}",
                file=sys.stderr,
                flush=True,
            )

        block = np.asarray(
            indata[:, 0],
            dtype=np.float32,
        ).copy()

        self.audio_blocks.append(block)

    def start(self) -> None:
        if self.stream is not None:
            raise RuntimeError("Recording is already active.")

        self.audio_blocks.clear()

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=1024,
            callback=self._audio_callback,
        )

        self.stream.start()

    def clear(self) -> None:
        """Discard audio captured so far without stopping the microphone."""
        if self.stream is None:
            raise RuntimeError("Recording is not active.")

        self.audio_blocks.clear()

    def stop(self) -> np.ndarray:
        if self.stream is None:
            raise RuntimeError("Recording is not active.")

        self.stream.stop()
        self.stream.close()
        self.stream = None

        if not self.audio_blocks:
            return np.empty(
                0,
                dtype=np.float32,
            )

        return np.concatenate(
            self.audio_blocks
        ).astype(
            np.float32,
            copy=False,
        )

    def close(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None


def send_message(**message: object) -> None:
    """Send one JSON message to nancee_chat.py."""

    print(
        json.dumps(message),
        flush=True,
    )


def main() -> int:
    transformers_logging.set_verbosity_error()

    print(
        f"[ASR] Loading Whisper once: {DEFAULT_MODEL}",
        file=sys.stderr,
        flush=True,
    )

    # WhisperTranscriber currently writes status messages to stdout.
    # Redirect those messages to stderr so stdout stays a clean JSON
    # communication channel for nancee_chat.py.
    with redirect_stdout(sys.stderr):
        transcriber = WhisperTranscriber(
            model_name=DEFAULT_MODEL,
            sample_rate=DEFAULT_SAMPLE_RATE,
        )

    recorder = PersistentRecorder(
        sample_rate=DEFAULT_SAMPLE_RATE,
    )

    print(
        "[ASR] Persistent worker ready.",
        file=sys.stderr,
        flush=True,
    )

    send_message(
        type="ready",
    )

    try:
        for raw_command in sys.stdin:
            command = raw_command.strip().upper()

            if command == "START":
                try:
                    recorder.start()

                    send_message(
                        type="started",
                    )

                except Exception as exc:
                    send_message(
                        type="error",
                        message=str(exc),
                    )

            elif command == "CLEAR":
                try:
                    recorder.clear()

                    send_message(
                        type="cleared",
                    )

                except Exception as exc:
                    send_message(
                        type="error",
                        message=str(exc),
                    )

            elif command == "STOP":
                try:
                    audio = recorder.stop()

                    if audio.size == 0:
                        send_message(
                            type="result",
                            text="",
                            duration=0.0,
                            transcription_seconds=0.0,
                            peak=0.0,
                        )
                        continue

                    duration = (
                        audio.size / DEFAULT_SAMPLE_RATE
                    )

                    peak = float(
                        np.max(np.abs(audio))
                    )

                    started_at = time.perf_counter()

                    text = transcriber.transcribe(
                        audio
                    )

                    transcription_seconds = (
                        time.perf_counter()
                        - started_at
                    )

                    send_message(
                        type="result",
                        text=text,
                        duration=duration,
                        transcription_seconds=transcription_seconds,
                        peak=peak,
                    )

                except Exception as exc:
                    recorder.close()

                    send_message(
                        type="error",
                        message=str(exc),
                    )

            elif command == "QUIT":
                recorder.close()

                send_message(
                    type="stopped",
                )

                return 0

            else:
                send_message(
                    type="error",
                    message=f"Unknown command: {command}",
                )

    except KeyboardInterrupt:
        pass

    finally:
        recorder.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
