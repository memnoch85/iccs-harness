import os

# Memory configuration
MEMORY_ACTIVE_TURN_LIMIT = int(
    os.getenv(
        "NANCEE_MEMORY_ACTIVE_TURN_LIMIT",
        "8",
    )
)

MEMORY_ACTIVE_CHARACTER_LIMIT = int(
    os.getenv(
        "NANCEE_MEMORY_ACTIVE_CHARACTER_LIMIT",
        "1600",
    )
)

MEMORY_KEEP_RECENT_TURNS = int(
    os.getenv(
        "NANCEE_MEMORY_KEEP_RECENT_TURNS",
        "2",
    )
)

MEMORY_RETRIEVAL_LIMIT = int(
    os.getenv(
        "NANCEE_MEMORY_RETRIEVAL_LIMIT",
        "2",
    )
)

MEMORY_RETRIEVAL_MIN_SCORE = float(
    os.getenv(
        "NANCEE_MEMORY_RETRIEVAL_MIN_SCORE",
        "2.0",
    )
)

if MEMORY_ACTIVE_TURN_LIMIT <= 2:
    raise ValueError("MEMORY_ACTIVE_TURN_LIMIT must be greater than 2.")

if MEMORY_ACTIVE_CHARACTER_LIMIT <= 0:
    raise ValueError("MEMORY_ACTIVE_CHARACTER_LIMIT must be positive.")

if MEMORY_KEEP_RECENT_TURNS < 0 or MEMORY_KEEP_RECENT_TURNS >= MEMORY_ACTIVE_TURN_LIMIT:
    raise ValueError(
        "MEMORY_KEEP_RECENT_TURNS must be zero or greater and "
        "smaller than MEMORY_ACTIVE_TURN_LIMIT."
    )

if MEMORY_RETRIEVAL_LIMIT <= 0:
    raise ValueError("MEMORY_RETRIEVAL_LIMIT must be positive.")

if MEMORY_RETRIEVAL_MIN_SCORE < 0:
    raise ValueError("MEMORY_RETRIEVAL_MIN_SCORE cannot be negative.")


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
        "1.2",
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
LLM_TEMPERATURE = 0.75
LLM_NUM_THREADS = 3
LLM_NUM_PREDICT = 120


# Timeout values
OLLAMA_STATUS_TIMEOUT = 5
OLLAMA_WARMUP_TIMEOUT = 90
OLLAMA_RESPONSE_TIMEOUT = 125


def load_system_prompt():
    with open(
        SYSTEM_PROMPT_FILE,
        "r",
        encoding="utf-8",
    ) as prompt_file:
        return prompt_file.read().strip()
