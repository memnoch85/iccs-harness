#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/nancee/sherpa/venv"
ASR_VENV="$ROOT/nancee/asr/venv"
PYTHON="$VENV/bin/python"

KOKORO_DIR="$ROOT/nancee/sherpa/kokoro-multi-lang-v1_0"
KOKORO_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2"

WARMUP_PROGRAM="$ROOT/nancee/sherpa/nancee-ollama-warmup"
WARMUP_SERVICE="$ROOT/nancee/sherpa/nancee-llm-warmup@.service"

LLM_MODEL="${LLM_MODEL:-llama3.2:3b}"

log() {
    printf '\n==> %s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

if [[ "$EUID" -eq 0 ]]; then
    die "Run setup.sh as your normal user, not with sudo."
fi

[[ -f "$ROOT/nancee/sherpa/nancee_chat.py" ]] \
    || die "setup.sh must be inside the iccs-harness repository root."

[[ -f "$ROOT/nancee/asr/asr_worker.py" ]] \
    || die "Missing nancee/asr/asr_worker.py."

[[ -f "$WARMUP_PROGRAM" ]] \
    || die "Missing the repository warmup program: $WARMUP_PROGRAM"

command -v apt-get >/dev/null 2>&1 \
    || die "This installer requires Raspberry Pi OS or Debian with apt."

log "Installing system packages"

sudo apt-get update

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    bzip2 \
    build-essential \
    ca-certificates \
    curl \
    git \
    libgomp1 \
    libopenblas0-pthread \
    libportaudio2 \
    libsndfile1 \
    libspa-0.2-bluetooth \
    pipewire \
    pipewire-alsa \
    pipewire-audio \
    pipewire-pulse \
    portaudio19-dev \
    pulseaudio-utils \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    sqlite3 \
    wget \
    wireplumber

if command -v pactl >/dev/null 2>&1; then
    server_name="$(
        pactl info 2>/dev/null \
            | awk -F': ' '/^Server Name:/ {print $2}' \
            || true
    )"

    if [[ "$server_name" == *PipeWire* ]]; then
        printf 'Audio server: %s\n' "$server_name"
    else
        printf 'WARNING: PipeWire is installed, but the active server is not reporting PipeWire.\n' >&2
        printf 'PulseAudio is not guaranteed to work with this harness. Reboot before running NANCEE.\n' >&2
    fi
fi

log "Installing Ollama"

if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh
fi

sudo systemctl enable --now ollama

for _ in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
        break
    fi

    sleep 1
done

curl -fsS http://127.0.0.1:11434/api/version >/dev/null \
    || die "Ollama did not start."

log "Downloading $LLM_MODEL"

ollama pull "$LLM_MODEL"

log "Creating one shared Python virtual environment"

if [[ -e "$VENV" && ! -x "$PYTHON" ]]; then
    rm -rf "$VENV"
fi

if [[ ! -x "$PYTHON" ]]; then
    python3 -m venv "$VENV"
fi

"$PYTHON" -m pip install --upgrade \
    pip \
    setuptools \
    wheel

"$PYTHON" -m pip install \
    numpy==2.2.6 \
    sounddevice==0.5.5 \
    sherpa-onnx==1.13.4 \
    sherpa-onnx-bin==1.13.4 \
    sherpa-onnx-core==1.13.4 \
    faster-whisper==1.2.1 \
    ctranslate2==4.8.1

# nancee_chat.py expects nancee/asr/venv/bin/python.
# Point that existing path at the same shared environment.
if [[ -e "$ASR_VENV" && ! -L "$ASR_VENV" ]]; then
    rm -rf "$ASR_VENV"
fi

ln -sfn ../sherpa/venv "$ASR_VENV"

log "Downloading Faster-Whisper base.en"

HF_HUB_OFFLINE=0 \
TRANSFORMERS_OFFLINE=0 \
"$PYTHON" - <<'PY'
from faster_whisper.utils import download_model

path = download_model("base.en")
print(f"Faster-Whisper model: {path}")
PY

log "Downloading the Kokoro ONNX model"

if [[ ! -s "$KOKORO_DIR/model.onnx" || ! -s "$KOKORO_DIR/voices.bin" ]]; then
    temporary_directory="$(mktemp -d)"
    archive="$temporary_directory/kokoro-multi-lang-v1_0.tar.bz2"

    trap 'rm -rf "$temporary_directory"' EXIT

    curl \
        --fail \
        --location \
        --retry 3 \
        --output "$archive" \
        "$KOKORO_URL"

    tar -xjf "$archive" -C "$ROOT/nancee/sherpa"

    rm -rf "$temporary_directory"
    trap - EXIT
fi

for required_file in \
    model.onnx \
    voices.bin \
    tokens.txt \
    lexicon-us-en.txt \
    lexicon-zh.txt
do
    [[ -s "$KOKORO_DIR/$required_file" ]] \
        || die "Kokoro installation is missing $required_file."
done

[[ -d "$KOKORO_DIR/espeak-ng-data" ]] \
    || die "Kokoro installation is missing espeak-ng-data."

log "Installing the existing Ollama warmup command"

chmod +x "$WARMUP_PROGRAM"

sudo tee /usr/local/bin/nancee-ollama-warmup >/dev/null <<EOF
#!/usr/bin/env bash
set -e
export PATH="$VENV/bin:\$PATH"
exec "$WARMUP_PROGRAM" "\$@"
EOF

sudo chmod 0755 /usr/local/bin/nancee-ollama-warmup

if [[ -f "$WARMUP_SERVICE" ]]; then
    log "Installing and enabling the existing warmup service"

    sudo install \
        -m 0644 \
        "$WARMUP_SERVICE" \
        /etc/systemd/system/nancee-llm-warmup@.service

    sudo systemctl daemon-reload

    sudo systemctl enable \
        "nancee-llm-warmup@${LLM_MODEL}.service"
else
    printf 'WARNING: %s was not found; the warmup command was installed, but no boot service was enabled.\n' \
        "$WARMUP_SERVICE" >&2
fi

log "Checking the Python runtime"

"$PYTHON" - <<'PY'
import sqlite3

import ctranslate2
import faster_whisper
import numpy
import sherpa_onnx
import sounddevice

connection = sqlite3.connect(":memory:")
connection.execute("CREATE VIRTUAL TABLE test_fts USING fts5(text)")
connection.close()

print("Python imports: OK")
print("SQLite FTS5: OK")
PY

log "Running unit tests"

chmod +x "$ROOT/nancee/test/run_unit_tests.sh"
bash "$ROOT/nancee/test/run_unit_tests.sh"

log "Running the existing Ollama warmup"

/usr/local/bin/nancee-ollama-warmup "$LLM_MODEL"

printf '\nInstallation complete.\n'
printf 'Run NANCEE with:\n\n'
printf '  cd "%s"\n' "$ROOT"
printf '  source nancee/sherpa/venv/bin/activate\n'
printf '  python3 nancee/sherpa/nancee_chat.py\n\n'
