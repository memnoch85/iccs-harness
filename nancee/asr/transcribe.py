#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd

# asr/ and sherpa/ are sibling directories. Add sherpa/ so this standalone
# worker and command-line tool use the same central NANCEE configuration.
NANCEE_ROOT = Path(__file__).resolve().parents[1]

if str(NANCEE_ROOT) not in sys.path:
    sys.path.insert(0, str(NANCEE_ROOT))

from sherpa.config import (  # noqa: E402
    ASR_BACKEND,
    ASR_BEAM_SIZE,
    ASR_COMPUTE_TYPE,
    ASR_MODEL,
    ASR_SAMPLE_RATE,
    ASR_THREADS,
    ASR_VAD_FILTER,
)

DEFAULT_BACKEND = ASR_BACKEND
DEFAULT_MODEL = ASR_MODEL
DEFAULT_SAMPLE_RATE = ASR_SAMPLE_RATE


def configure_backend_logging():
    """Silence noncritical backend logging without importing both backends."""
    if DEFAULT_BACKEND == "hf_direct":
        from transformers.utils import (  # pyright: ignore[reportMissingImports]
            logging as transformers_logging,
        )

        transformers_logging.set_verbosity_error()


def parse_device(value: str | None) -> int | str | None:
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
        device: int | str | None = None,
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

        block = np.asarray(
            indata[:, 0],
            dtype=np.float32,
        ).copy()

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

        return np.concatenate(
            self.audio_blocks
        ).astype(
            np.float32,
            copy=False,
        )


class WhisperTranscriber:
    """Load one configured Whisper backend and reuse it for every recording."""

    def __init__(
        self,
        model_name=DEFAULT_MODEL,
        sample_rate=DEFAULT_SAMPLE_RATE,
        backend=DEFAULT_BACKEND,
        compute_type=ASR_COMPUTE_TYPE,
        cpu_threads=ASR_THREADS,
        beam_size=ASR_BEAM_SIZE,
        vad_filter=ASR_VAD_FILTER,
    ):
        self.model_name = str(model_name).strip()
        self.sample_rate = int(sample_rate)
        self.backend = str(backend).strip().lower()
        self.compute_type = str(compute_type).strip().lower()
        self.cpu_threads = int(cpu_threads)
        self.beam_size = int(beam_size)
        self.vad_filter = bool(vad_filter)

        self.asr_pipeline: Any | None = None
        self.whisper_model: Any | None = None

        print(
            "[ASR] Loading "
            f"backend={self.backend} "
            f"model={self.model_name} "
            f"compute_type={self.compute_type} "
            f"threads={self.cpu_threads} "
            f"beam_size={self.beam_size} "
            f"vad_filter={str(self.vad_filter).lower()}",
            flush=True,
        )

        if self.backend == "faster_whisper":
            self._load_faster_whisper()
        elif self.backend == "hf_direct":
            self._load_hf_direct()
        else:
            raise ValueError(
                "Unsupported ASR backend: "
                f"{self.backend!r}"
            )

        print("[ASR] Whisper loaded.", flush=True)

    def _load_faster_whisper(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Faster-Whisper is selected but is not installed in the "
                "production ASR virtual environment. Install it with:\n"
                f'  "{sys.executable}" -m pip install '
                "faster-whisper==1.2.1 ctranslate2==4.8.1"
            ) from exc

        self.whisper_model = WhisperModel(
            self.model_name,
            device="cpu",
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )

    def _load_hf_direct(self):
        from transformers import pipeline  # pyright: ignore[reportMissingImports]
        from transformers.utils import (  # pyright: ignore[reportMissingImports]
            logging as transformers_logging,
        )

        transformers_logging.set_verbosity_error()

        self.asr_pipeline = pipeline(
            task="automatic-speech-recognition",
            model=self.model_name,
            device=-1,
        )

        model = getattr(
            self.asr_pipeline,
            "model",
            None,
        )
        generation_config = getattr(
            model,
            "generation_config",
            None,
        )

        if generation_config is not None:
            setattr(
                generation_config,
                "forced_decoder_ids",
                None,
            )

    def transcribe(self, audio):
        if audio.size == 0:
            return ""

        if self.backend == "faster_whisper":
            whisper_model = self.whisper_model

            if whisper_model is None:
                raise RuntimeError(
                    "Faster-Whisper was selected but the model "
                    "was not initialized."
                )

            segments, _info = whisper_model.transcribe(
                audio,
                language="en",
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
            )

            return "".join(
                str(segment.text)
                for segment in segments
            ).strip()

        asr_pipeline = self.asr_pipeline

        if asr_pipeline is None:
            raise RuntimeError(
                "The Hugging Face ASR pipeline was not initialized."
            )

        result = asr_pipeline(
            {
                "array": audio,
                "sampling_rate": self.sample_rate,
            },
            return_timestamps=False,
        )

        if isinstance(result, dict):
            return str(result.get("text", "")).strip()

        return str(result).strip()


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Push-to-talk microphone transcription using the "
            "configured NANCEE ASR backend."
        )
    )

    parser.add_argument(
        "--backend",
        default=DEFAULT_BACKEND,
        choices=("faster_whisper", "hf_direct"),
        help=f"ASR backend. Default: {DEFAULT_BACKEND}",
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


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return 0

    device = parse_device(args.device)
    configure_backend_logging()

    recorder = PushToTalkRecorder(
        sample_rate=DEFAULT_SAMPLE_RATE,
        device=device,
    )

    transcriber = WhisperTranscriber(
        model_name=args.model,
        sample_rate=DEFAULT_SAMPLE_RATE,
        backend=args.backend,
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
                "Transcription completed in "
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
