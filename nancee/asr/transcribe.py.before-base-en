#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional, Union

import numpy as np
import sounddevice as sd
from transformers import pipeline
from transformers.utils import logging as transformers_logging


DEFAULT_MODEL = "openai/whisper-tiny.en"
DEFAULT_SAMPLE_RATE = 16_000


def parse_device(value: Optional[str]) -> Optional[Union[int, str]]:
    """
    Convert a numeric device argument into an integer.

    A nonnumeric value is treated as a sounddevice device name.
    These device numbers are not the same as wpctl node IDs.
    """
    if value is None:
        return None

    value = value.strip()

    if value.isdigit():
        return int(value)

    return value


class PushToTalkRecorder:
    """Record microphone audio until the user presses Enter."""

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        device: Optional[Union[int, str]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.device = device

        self.audio_blocks: list[np.ndarray] = []
        self.stream_warnings: list[str] = []

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
            self.stream_warnings.append(str(status))

        # The stream is configured as mono, so select channel zero.
        block = np.asarray(indata[:, 0], dtype=np.float32).copy()
        self.audio_blocks.append(block)

    def record(self) -> np.ndarray:
        """Begin recording and stop when Enter is pressed."""

        self.audio_blocks.clear()
        self.stream_warnings.clear()

        try:
            sd.check_input_settings(
                device=self.device,
                channels=1,
                dtype="float32",
                samplerate=self.sample_rate,
            )

            with sd.InputStream(
                device=self.device,
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=1024,
                callback=self._audio_callback,
            ):
                input("Recording... Press Enter to stop.\n")

        except sd.PortAudioError as exc:
            raise RuntimeError(
                f"Unable to open the microphone: {exc}"
            ) from exc

        for warning in self.stream_warnings:
            print(
                f"Microphone warning: {warning}",
                file=sys.stderr,
            )

        if not self.audio_blocks:
            return np.empty(0, dtype=np.float32)

        return np.concatenate(self.audio_blocks).astype(
            np.float32,
            copy=False,
        )


class WhisperTranscriber:
    """Load Whisper once and reuse it for each recording."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> None:
        self.model_name = model_name
        self.sample_rate = sample_rate

        print(f"Loading Whisper model: {model_name}", flush=True)

        self.asr_pipeline = pipeline(
            task="automatic-speech-recognition",
            model=model_name,
            device=-1,  # Run on the Raspberry Pi CPU.
        )

        # Avoid the deprecated forced_decoder_ids behavior.
        generation_config = self.asr_pipeline.model.generation_config
        generation_config.forced_decoder_ids = None

        print("Whisper loaded.", flush=True)

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""

        result = self.asr_pipeline(
            {
                "array": audio,
                "sampling_rate": self.sample_rate,
            },
            return_timestamps=False,
        )

        return str(result.get("text", "")).strip()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Push-to-talk microphone transcription using Whisper."
        )
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Whisper model. Default: {DEFAULT_MODEL}",
    )

    parser.add_argument(
        "--device",
        help=(
            "sounddevice input number or device name. "
            "This is not a wpctl node ID."
        ),
    )

    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available sounddevice devices and exit.",
    )

    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return 0

    device = parse_device(args.device)

    # Reduce the large amount of noncritical Transformers logging.
    transformers_logging.set_verbosity_error()

    recorder = PushToTalkRecorder(
        sample_rate=DEFAULT_SAMPLE_RATE,
        device=device,
    )

    transcriber = WhisperTranscriber(
        model_name=args.model,
        sample_rate=DEFAULT_SAMPLE_RATE,
    )

    print()
    print("Push-to-talk is ready.")
    print("Press Enter to start recording.")
    print("Press Enter again to stop and transcribe.")
    print("Press Ctrl+C to exit.")

    try:
        while True:
            input("\nPress Enter to start recording...")

            audio = recorder.record()

            if audio.size == 0:
                print("No microphone audio was captured.")
                continue

            duration = audio.size / DEFAULT_SAMPLE_RATE
            peak_level = float(np.max(np.abs(audio)))

            print(
                f"Captured {duration:.2f} seconds "
                f"(peak level: {peak_level:.4f}).",
                flush=True,
            )

            if peak_level < 0.0001:
                print(
                    "Warning: the recording appears to contain silence. "
                    "Check that the microphone is unmuted.",
                    flush=True,
                )

            print("Transcribing...", flush=True)

            transcription_started = time.perf_counter()

            text = transcriber.transcribe(audio)

            transcription_seconds = (
                time.perf_counter() - transcription_started
            )

            print(
                f"Transcription completed in "
                f"{transcription_seconds:.2f} seconds.",
                flush=True,
            )

            if text:
                print(f"\nYou: {text}")
            else:
                print("\nNo speech recognized.")

    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except RuntimeError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        print(
            "Run with --list-devices to inspect the available inputs.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
