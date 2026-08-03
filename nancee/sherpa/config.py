import os
from pathlib import Path

# Short-term memory / recall configuration
MEMORY_RECALL_TURN_LIMIT = int(
    os.getenv(
        "NANCEE_MEMORY_RECALL_TURN_LIMIT",
        "384",
    )
)

MEMORY_RECENT_PROMPT_TURNS = int(
    os.getenv(
        "NANCEE_MEMORY_RECENT_PROMPT_TURNS",
        "1",
    )
)

MEMORY_RECALL_ENABLED = (
    os.getenv(
        "NANCEE_MEMORY_RECALL_ENABLED",
        "true",
    ).lower()
    == "true"
)

MEMORY_RECALL_LIMIT = int(
    os.getenv(
        "NANCEE_MEMORY_RECALL_LIMIT",
        "3",
    )
)

MEMORY_RECALL_CONTEXT_MAX_CHARACTERS = int(
    os.getenv(
        "NANCEE_MEMORY_RECALL_CONTEXT_MAX_CHARACTERS",
        "650",
    )
)

if MEMORY_RECALL_TURN_LIMIT <= 0:
    raise ValueError("MEMORY_RECALL_TURN_LIMIT must be positive.")

if MEMORY_RECENT_PROMPT_TURNS < 0:
    raise ValueError("MEMORY_RECENT_PROMPT_TURNS cannot be negative.")

if MEMORY_RECALL_LIMIT <= 0:
    raise ValueError("MEMORY_RECALL_LIMIT must be positive.")

if MEMORY_RECALL_CONTEXT_MAX_CHARACTERS <= 0:
    raise ValueError("MEMORY_RECALL_CONTEXT_MAX_CHARACTERS must be positive.")

# NANCEE ASR RUNTIME CONFIG v1 START
#
# The benchmark winner is Faster-Whisper Base.en using INT8 on four CPU
# threads. These values may be overridden with NANCEE_* environment variables.
ASR_BACKEND = os.getenv(
    "NANCEE_ASR_BACKEND",
    "faster_whisper",
).strip().lower()

if ASR_BACKEND not in {
    "faster_whisper",
    "hf_direct",
}:
    raise ValueError(
        "NANCEE_ASR_BACKEND must be "
        "'faster_whisper' or 'hf_direct'."
    )

# The two backends use different model identifiers.
_default_asr_model = (
    "base.en"
    if ASR_BACKEND == "faster_whisper"
    else "openai/whisper-base.en"
)

ASR_MODEL = os.getenv(
    "NANCEE_ASR_MODEL",
    _default_asr_model,
).strip()

ASR_COMPUTE_TYPE = os.getenv(
    "NANCEE_ASR_COMPUTE_TYPE",
    "int8",
).strip().lower()

ASR_THREADS = int(
    os.getenv(
        "NANCEE_ASR_THREADS",
        "4",
    )
)

ASR_BEAM_SIZE = int(
    os.getenv(
        "NANCEE_ASR_BEAM_SIZE",
        "1",
    )
)

ASR_VAD_FILTER = (
    os.getenv(
        "NANCEE_ASR_VAD_FILTER",
        "false",
    ).lower()
    == "true"
)

ASR_SAMPLE_RATE = int(
    os.getenv(
        "NANCEE_ASR_SAMPLE_RATE",
        "16000",
    )
)

if not ASR_MODEL:
    raise ValueError("NANCEE_ASR_MODEL cannot be empty.")

if ASR_THREADS <= 0:
    raise ValueError("NANCEE_ASR_THREADS must be positive.")

if ASR_BEAM_SIZE <= 0:
    raise ValueError("NANCEE_ASR_BEAM_SIZE must be positive.")

if ASR_SAMPLE_RATE <= 0:
    raise ValueError("NANCEE_ASR_SAMPLE_RATE must be positive.")

# NANCEE ASR RUNTIME CONFIG v1 END


# Sherpa/Kokoro configuration
SHERPA_DIRECTORY = Path(__file__).resolve().parent

MODEL_DIR = str(
    Path(
        os.environ.get(
            "SHERPA_MODEL_DIR",
            SHERPA_DIRECTORY / "kokoro-multi-lang-v1_0",
        )
    ).expanduser()
)
VOICE_ID = int(
    os.environ.get(
        "VOICE_ID",
        "3",
    )
)

SPEED = float(
    os.environ.get(
        "SPEED",
        "1.25",
    )
)

TTS_GREETING_BRIDGE_SPEED = float(
    os.getenv(
        "NANCEE_TTS_GREETING_BRIDGE_SPEED",
        "1.1",
    )
)

if TTS_GREETING_BRIDGE_SPEED <= 0:
    raise ValueError("TTS_GREETING_BRIDGE_SPEED must be greater than zero.")


TTS_FILLER_SPEED = float(
    os.getenv(
        "NANCEE_TTS_FILLER_SPEED",
        "1.0",
    )
)

if TTS_FILLER_SPEED <= 0:
    raise ValueError("TTS_FILLER_SPEED must be greater than zero.")

TTS_EMPHASIS_SPEED = float(
    os.getenv(
        "TTS_EMPHASIS_SPEED",
        "0.80",
    )
)

NUM_THREADS = int(
    os.environ.get(
        "SHERPA_THREADS",
        "3",
    )
)

BLOCKSIZE = int(
    os.environ.get(
        "BLOCKSIZE",
        "1024",
    )
)

PREROLL_MS = int(
    os.environ.get(
        "PREROLL_MS",
        "0",
    )
)

TTS_SILENCE_SCALE = 0.2
TTS_MAX_NUM_SENTENCES = 1


if TTS_EMPHASIS_SPEED <= 0:
    raise ValueError("TTS_EMPHASIS_SPEED must be greater than zero.")


# Text chunking configuration
FIRST_CHUNK_MIN_WORDS = int(
    os.environ.get(
        "FIRST_CHUNK_MIN_WORDS",
        "1",
    )
)


FIRST_CHUNK_MAX_WORDS = int(
    os.environ.get(
        "FIRST_CHUNK_MAX_WORDS",
        "4",
    )
)


if FIRST_CHUNK_MIN_WORDS <= 0:
    raise ValueError("FIRST_CHUNK_MIN_WORDS must be positive.")

# Ollama configuration
OLLAMA_URL = os.environ.get(
    "OLLAMA_URL",
    "http://localhost:11434/api/chat",
).strip()

OLLAMA_PS_URL = os.environ.get(
    "OLLAMA_PS_URL",
    "http://127.0.0.1:11434/api/ps",
).strip()

OLLAMA_WARMUP_COMMAND = os.environ.get(
    "OLLAMA_WARMUP_COMMAND",
    "/usr/local/bin/nancee-ollama-warmup",
).strip()

LLM_MODEL = os.environ.get(
    "LLM_MODEL",
    "llama3.2:3b",
)

SYSTEM_PROMPT_FILE = os.environ.get(
    "NANCEE_SYSTEM_PROMPT_FILE",
    str(Path(__file__).resolve().with_name("system-prompt.txt")),
)


# Ollama generation settings
LLM_TEMPERATURE = float(
    os.environ.get(
        "NANCEE_LLM_TEMPERATURE",
        "0.3",
    )
)
LLM_NUM_THREADS = int(
    os.environ.get(
        "NANCEE_LLM_NUM_THREADS",
        "4",
    )
)
LLM_NUM_PREDICT = int(
    os.environ.get(
        "NANCEE_LLM_NUM_PREDICT",
        "120",
    )
)


# Timeout values
OLLAMA_STATUS_TIMEOUT = 5
OLLAMA_WARMUP_TIMEOUT = 125
OLLAMA_RESPONSE_TIMEOUT = 115


def load_system_prompt():
    with open(
        SYSTEM_PROMPT_FILE,
        "r",
        encoding="utf-8",
    ) as prompt_file:
        return prompt_file.read().strip()


# Memory debug logging.
# Enable with:
#export NANCEE_MEMORY_DEBUG=true
MEMORY_DEBUG_ENABLED = (
    os.getenv(
        "NANCEE_MEMORY_DEBUG",
        "false",
    ).lower()
    == "true"
)

# Latency bridge configuration.
LATENCY_BRIDGE_ENABLED = (
    os.getenv(
        "NANCEE_LATENCY_BRIDGE_ENABLED",
        "true",
    ).lower()
    == "true"
)

LATENCY_BRIDGE_GREETING_SECONDS = float(
    os.getenv(
        "NANCEE_LATENCY_BRIDGE_GREETING_SECONDS",
        "7.3",
    )
)

LATENCY_BRIDGE_NORMAL_SECONDS = float(
    os.getenv(
        "NANCEE_LATENCY_BRIDGE_NORMAL_SECONDS",
        "4.5",
    )
)

LATENCY_BRIDGE_RECALL_SECONDS = float(
    os.getenv(
        "NANCEE_LATENCY_BRIDGE_RECALL_SECONDS",
        "5.0",

    )
)

if LATENCY_BRIDGE_GREETING_SECONDS <= 0:
    raise ValueError("LATENCY_BRIDGE_GREETING_SECONDS must be greater than zero.")

if LATENCY_BRIDGE_NORMAL_SECONDS <= 0:
    raise ValueError("LATENCY_BRIDGE_NORMAL_SECONDS must be greater than zero.")

if LATENCY_BRIDGE_RECALL_SECONDS <= 0:
    raise ValueError("LATENCY_BRIDGE_RECALL_SECONDS must be greater than zero.")

LATENCY_BRIDGE_PHRASES = (
    "Just one second please,",
    "Give me one moment,",
    "Let me think briefly,",
    "Umm, one moment please,",
    "Hang on one moment,",
)

LATENCY_BRIDGE_GREETING_PHRASES = (
    "umm...",
    "humm..."
)

for phrase in LATENCY_BRIDGE_GREETING_PHRASES:
    word_total = len(phrase.split())

    if not 1 <= word_total <= 4:
        raise ValueError(
            f"Greeting latency bridge phrase must contain one to four words: {phrase!r}"
        )


for phrase in LATENCY_BRIDGE_PHRASES:
    if len(phrase.split()) != 4:
        raise ValueError(f"Latency bridge phrase must contain four words: {phrase!r}")

# Later-response semantic chunking.
LATER_CHUNK_MIN_WORDS = int(os.getenv("NANCEE_LATER_CHUNK_MIN_WORDS", "4"))
LATER_CHUNK_TARGET_WORDS = int(os.getenv("NANCEE_LATER_CHUNK_TARGET_WORDS", "6"))
LATER_CHUNK_MAX_WORDS = int(os.getenv("NANCEE_LATER_CHUNK_MAX_WORDS", "9"))

if not (
    1 <= LATER_CHUNK_MIN_WORDS <= LATER_CHUNK_TARGET_WORDS <= LATER_CHUNK_MAX_WORDS
):
    raise ValueError("Later chunk limits must satisfy 1 <= min <= target <= max.")

TTS_GAP_FILLER_ENABLED = (
    os.getenv("NANCEE_TTS_GAP_FILLER_ENABLED", "true").lower() == "true"
)
TTS_GAP_FILLER_COOLDOWN_SECONDS = 9.5
TTS_GAP_FILLER_SECONDS = float(os.getenv("NANCEE_TTS_GAP_FILLER_SECONDS", "3.5"))
TTS_GAP_FILLER_MAX_PER_TURN = int(os.getenv("NANCEE_TTS_GAP_FILLER_MAX_PER_TURN", "5"))
TTS_GAP_FILLER_PHRASES = ("humm...", "Umm...")

if TTS_GAP_FILLER_SECONDS <= 0:
    raise ValueError("TTS_GAP_FILLER_SECONDS must be positive")
if TTS_GAP_FILLER_MAX_PER_TURN < 0:
    raise ValueError("TTS_GAP_FILLER_MAX_PER_TURN cannot be negative")

# Intent-aware response policy tunables.
# These are per-request generation limits. The global LLM_NUM_PREDICT
# remains the fallback for callers that do not select a response policy.
RESPONSE_GREETING_NUM_PREDICT = int(
    os.getenv("NANCEE_RESPONSE_GREETING_NUM_PREDICT", "8")
)
RESPONSE_GREETING_TEMPERATURE = float(
    os.getenv("NANCEE_RESPONSE_GREETING_TEMPERATURE", "0.10")
)

RESPONSE_ACK_NUM_PREDICT = int(os.getenv("NANCEE_RESPONSE_ACK_NUM_PREDICT", "18"))
RESPONSE_ACK_TEMPERATURE = float(os.getenv("NANCEE_RESPONSE_ACK_TEMPERATURE", "0.25"))

RESPONSE_DIRECTIVE_NUM_PREDICT = int(
    os.getenv(
        "NANCEE_RESPONSE_DIRECTIVE_NUM_PREDICT",
        "58",
    )
)
RESPONSE_DIRECTIVE_TEMPERATURE = float(
    os.getenv(
        "NANCEE_RESPONSE_DIRECTIVE_TEMPERATURE",
        "0.20",
    )
)

RESPONSE_CLARIFY_NUM_PREDICT = int(
    os.getenv("NANCEE_RESPONSE_CLARIFY_NUM_PREDICT", "18")
)
RESPONSE_CLARIFY_TEMPERATURE = float(
    os.getenv("NANCEE_RESPONSE_CLARIFY_TEMPERATURE", "0.20")
)

RESPONSE_NORMAL_NUM_PREDICT = int(os.getenv("NANCEE_RESPONSE_NORMAL_NUM_PREDICT", "48"))
RESPONSE_NORMAL_TEMPERATURE = float(
    os.getenv("NANCEE_RESPONSE_NORMAL_TEMPERATURE", "0.28")
)

RESPONSE_DETAILED_NUM_PREDICT = int(
    os.getenv("NANCEE_RESPONSE_DETAILED_NUM_PREDICT", "120")
)
RESPONSE_DETAILED_TEMPERATURE = float(
    os.getenv("NANCEE_RESPONSE_DETAILED_TEMPERATURE", "0.28")
)

RESPONSE_RECALL_NUM_PREDICT = int(os.getenv("NANCEE_RESPONSE_RECALL_NUM_PREDICT", "18"))
RESPONSE_RECALL_TEMPERATURE = float(
    os.getenv("NANCEE_RESPONSE_RECALL_TEMPERATURE", "0.14")
)

for _setting_name, _setting_value in (
    ("RESPONSE_GREETING_NUM_PREDICT", RESPONSE_GREETING_NUM_PREDICT),
    ("RESPONSE_ACK_NUM_PREDICT", RESPONSE_ACK_NUM_PREDICT),
    (
        "RESPONSE_DIRECTIVE_NUM_PREDICT",
        RESPONSE_DIRECTIVE_NUM_PREDICT,
    ),
    ("RESPONSE_CLARIFY_NUM_PREDICT", RESPONSE_CLARIFY_NUM_PREDICT),
    ("RESPONSE_NORMAL_NUM_PREDICT", RESPONSE_NORMAL_NUM_PREDICT),
    ("RESPONSE_DETAILED_NUM_PREDICT", RESPONSE_DETAILED_NUM_PREDICT),
    ("RESPONSE_RECALL_NUM_PREDICT", RESPONSE_RECALL_NUM_PREDICT),
):
    if _setting_value <= 0:
        raise ValueError(f"{_setting_name} must be positive.")

for _setting_name, _setting_value in (
    ("RESPONSE_GREETING_TEMPERATURE", RESPONSE_GREETING_TEMPERATURE),
    ("RESPONSE_ACK_TEMPERATURE", RESPONSE_ACK_TEMPERATURE),
    (
        "RESPONSE_DIRECTIVE_TEMPERATURE",
        RESPONSE_DIRECTIVE_TEMPERATURE,
    ),
    ("RESPONSE_CLARIFY_TEMPERATURE", RESPONSE_CLARIFY_TEMPERATURE),
    ("RESPONSE_NORMAL_TEMPERATURE", RESPONSE_NORMAL_TEMPERATURE),
    ("RESPONSE_DETAILED_TEMPERATURE", RESPONSE_DETAILED_TEMPERATURE),
    ("RESPONSE_RECALL_TEMPERATURE", RESPONSE_RECALL_TEMPERATURE),
):
    if _setting_value < 0:
        raise ValueError(f"{_setting_name} cannot be negative.")
