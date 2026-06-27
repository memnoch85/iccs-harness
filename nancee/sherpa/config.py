import os

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

#Ollama configuration
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

#Ollama generation settings
LLM_TEMPERATURE = 0.75
LLM_NUM_THREADS = 3
LLM_NUM_PREDICT = 120

#timeout values
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
