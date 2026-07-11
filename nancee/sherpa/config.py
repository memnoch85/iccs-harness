import os


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

MEMORY_RECALL_MIN_SCORE = float(
    os.getenv(
        "NANCEE_MEMORY_RECALL_MIN_SCORE",
        "2.0",
    )
)

MEMORY_RECALL_CONTEXT_MAX_CHARACTERS = int(
    os.getenv(
        "NANCEE_MEMORY_RECALL_CONTEXT_MAX_CHARACTERS",
        "650",
    )
)

MEMORY_RECALL_SNIPPET_WORDS = int(
    os.getenv(
        "NANCEE_MEMORY_RECALL_SNIPPET_WORDS",
        "18",
    )
)


if MEMORY_RECALL_TURN_LIMIT <= 0:
    raise ValueError("MEMORY_RECALL_TURN_LIMIT must be positive.")

if MEMORY_RECENT_PROMPT_TURNS < 0:
    raise ValueError("MEMORY_RECENT_PROMPT_TURNS cannot be negative.")

if MEMORY_RECALL_LIMIT <= 0:
    raise ValueError("MEMORY_RECALL_LIMIT must be positive.")

if MEMORY_RECALL_MIN_SCORE < 0:
    raise ValueError("MEMORY_RECALL_MIN_SCORE cannot be negative.")

if MEMORY_RECALL_CONTEXT_MAX_CHARACTERS <= 0:
    raise ValueError("MEMORY_RECALL_CONTEXT_MAX_CHARACTERS must be positive.")

if MEMORY_RECALL_SNIPPET_WORDS <= 0:
    raise ValueError("MEMORY_RECALL_SNIPPET_WORDS must be positive.")

# Stable user profile configuration.
# This is not FTS5 recall. It is a small, explicit profile overlay.
USER_PROFILE_FILE = os.getenv(
    "NANCEE_USER_PROFILE_FILE",
    "/home/memnoch/Nancee/nancee/sherpa/user_profile.json",
)

USER_PROFILE_CONTEXT_MAX_CHARACTERS = int(
    os.getenv(
        "NANCEE_USER_PROFILE_CONTEXT_MAX_CHARACTERS",
        "1000",
    )
)

if USER_PROFILE_CONTEXT_MAX_CHARACTERS <= 0:
    raise ValueError("USER_PROFILE_CONTEXT_MAX_CHARACTERS must be positive.")


# Sherpa/Kokoro configuration
MODEL_DIR = os.environ.get(
    "SHERPA_MODEL_DIR",
    "kokoro-multi-lang-v1_0",
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
        "1.3",
    )
)

TTS_EMPHASIS_SPEED = float(
    os.getenv(
        "TTS_EMPHASIS_SPEED",
        "0.80",
    )
)

NUM_THREADS = int(
    os.environ.get(
        "SHERPA_THREADS",
        "4",
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

TARGET_CHUNK_WORDS = int(
    os.environ.get(
        "TARGET_CHUNK_WORDS",
        "4",
    )
)

MAX_CHUNK_WORDS = int(
    os.environ.get(
        "MAX_CHUNK_WORDS",
        "8",
    )
)


if FIRST_CHUNK_MIN_WORDS <= 0:
    raise ValueError("FIRST_CHUNK_MIN_WORDS must be positive.")

if TARGET_CHUNK_WORDS <= 0:
    raise ValueError("TARGET_CHUNK_WORDS must be positive.")

if MAX_CHUNK_WORDS <= 0:
    raise ValueError("MAX_CHUNK_WORDS must be positive.")


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
    "phi4-mini:3.8b",
)

SYSTEM_PROMPT_FILE = os.environ.get(
    "NANCEE_SYSTEM_PROMPT_FILE",
    "/home/memnoch/Nancee/nancee/sherpa/system-prompt.txt",
)


# Ollama generation settings
LLM_TEMPERATURE = 0.3
LLM_NUM_THREADS = 3
LLM_NUM_PREDICT = 32


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
#   export NANCEE_MEMORY_DEBUG=true
MEMORY_DEBUG_ENABLED = (
    os.getenv(
        "NANCEE_MEMORY_DEBUG",
        "false",
    ).lower()
    == "true"
)

