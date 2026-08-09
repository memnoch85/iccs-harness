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

LLM_MODEL="llama3.2:3b"
WARMUP_UNIT="nancee-llm-warmup@${LLM_MODEL}.service"

INSTALL_USER="$(id -un)"
INSTALL_GROUP="$(id -gn)"
INSTALL_HOME="$HOME"

TEMPORARY_DIRECTORY=""

log() {
    printf '\n==> %s\n' "$*"
}

die() {
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [[ -n "$TEMPORARY_DIRECTORY" ]]; then
        rm -rf "$TEMPORARY_DIRECTORY"
    fi
}

trap cleanup EXIT

if [[ "$EUID" -eq 0 ]]; then
    die "Run setup.sh as your normal user, not with sudo."
fi

command -v sudo >/dev/null 2>&1 \
    || die "sudo is required."

command -v apt-get >/dev/null 2>&1 \
    || die "This installer requires Raspberry Pi OS or Debian with apt."

[[ -f "$ROOT/nancee/sherpa/nancee_chat.py" ]] \
    || die "setup.sh must be inside the iccs-harness repository root."

[[ -f "$ROOT/nancee/asr/asr_worker.py" ]] \
    || die "Missing nancee/asr/asr_worker.py."

[[ -f "$WARMUP_PROGRAM" ]] \
    || die "Missing warmup program: $WARMUP_PROGRAM"

[[ -f "$WARMUP_SERVICE" ]] \
    || die "Missing warmup service: $WARMUP_SERVICE"


log "Installing system packages"

sudo apt-get update

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    bzip2 \
    build-essential \
    ca-certificates \
    curl \
    libgomp1 \
    libopenblas0-pthread \
    libportaudio2 \
    libsndfile1 \
    libspa-0.2-bluetooth \
    pipewire \
    pipewire-alsa \
    pipewire-pulse \
    portaudio19-dev \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    sqlite3 \
    wireplumber


log "Checking PipeWire services"

if systemctl --user is-active --quiet pipewire.service 2>/dev/null \
    && systemctl --user is-active --quiet pipewire-pulse.service 2>/dev/null \
    && systemctl --user is-active --quiet wireplumber.service 2>/dev/null
then
    printf 'PipeWire audio services: active\n'
else
    printf 'WARNING: PipeWire was installed, but its user services are not all active.\n' >&2
    printf 'Reboot before running the ICCS Voice Harness.\n' >&2
fi


log "Installing Ollama"

if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh
fi

sudo systemctl enable --now ollama.service

for _ in {1..60}; do
    if curl \
        -fsS \
        http://127.0.0.1:11434/api/version \
        >/dev/null 2>&1
    then
        break
    fi

    sleep 1
done

curl \
    -fsS \
    http://127.0.0.1:11434/api/version \
    >/dev/null \
    || die "Ollama did not start."


log "Downloading $LLM_MODEL"

ollama pull "$LLM_MODEL"


log "Creating the shared Python virtual environment"

if [[ -e "$VENV" || -L "$VENV" ]]; then
    if [[ ! -x "$PYTHON" ]]; then
        rm -rf "$VENV"
    fi
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


log "Linking the ASR environment to the shared environment"

if [[ -e "$ASR_VENV" || -L "$ASR_VENV" ]]; then
    rm -rf "$ASR_VENV"
fi

ln -s ../sherpa/venv "$ASR_VENV"


log "Downloading Faster-Whisper base.en"

HF_HUB_OFFLINE=0 \
TRANSFORMERS_OFFLINE=0 \
HF_HUB_DISABLE_TELEMETRY=1 \
"$PYTHON" - <<'PY'
from faster_whisper.utils import download_model

model_path = download_model("base.en")
print(f"Faster-Whisper model: {model_path}")
PY


kokoro_is_complete() {
    local required_file

    for required_file in \
        model.onnx \
        voices.bin \
        tokens.txt \
        lexicon-us-en.txt \
        lexicon-zh.txt
    do
        [[ -s "$KOKORO_DIR/$required_file" ]] || return 1
    done

    [[ -d "$KOKORO_DIR/espeak-ng-data" ]]
}


log "Checking the Kokoro ONNX model"

if ! kokoro_is_complete; then
    log "Downloading the Kokoro ONNX model"

    TEMPORARY_DIRECTORY="$(mktemp -d)"
    ARCHIVE="$TEMPORARY_DIRECTORY/kokoro-multi-lang-v1_0.tar.bz2"

    curl \
        --fail \
        --location \
        --retry 3 \
        --output "$ARCHIVE" \
        "$KOKORO_URL"

    rm -rf "$KOKORO_DIR"

    tar \
        -xjf "$ARCHIVE" \
        -C "$ROOT/nancee/sherpa"

    kokoro_is_complete \
        || die "The Kokoro model archive did not contain all required files."

    rm -rf "$TEMPORARY_DIRECTORY"
    TEMPORARY_DIRECTORY=""
else
    printf 'Kokoro model: already installed\n'
fi


log "Checking the Python runtime"

"$PYTHON" - <<'PY'
import sqlite3
from importlib.metadata import version

import ctranslate2
import faster_whisper
import numpy
import sherpa_onnx
import sounddevice

connection = sqlite3.connect(":memory:")
connection.execute(
    "CREATE VIRTUAL TABLE test_fts USING fts5(text)"
)
connection.close()

print(f"Python imports: OK")
print(f"NumPy: {version('numpy')}")
print(f"sounddevice: {version('sounddevice')}")
print(f"Sherpa ONNX: {version('sherpa-onnx')}")
print(f"Faster-Whisper: {version('faster-whisper')}")
print(f"CTranslate2: {version('ctranslate2')}")
print(f"SQLite: {sqlite3.sqlite_version}")
print("SQLite FTS5: OK")
PY


log "Running unit tests"

PATH="$VENV/bin:$PATH" \

# Begin:: Build routerMon from training source
ROUTERMON_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROUTERMON_PYTHON="$ROUTERMON_ROOT/nancee/sherpa/venv/bin/python"

echo "[SETUP] Installing routerMon training dependencies..."
"$ROUTERMON_PYTHON" -m pip install "scikit-learn==1.9.0" joblib

echo "[SETUP] Training routerMon..."
"$ROUTERMON_PYTHON" \
    "$ROUTERMON_ROOT/nancee/router_training/train_router_mon.py"

echo "[SETUP] Installing routerMon runtime model..."
cp \
    "$ROUTERMON_ROOT/nancee/router_training/routerMon.joblib" \
    "$ROUTERMON_ROOT/nancee/sherpa/routerMon.joblib"

echo "[SETUP] routerMon ready."
# End:: Build routerMon from training source

    bash "$ROOT/nancee/test/run_unit_tests.sh"


log "Installing the existing Ollama warmup command"

chmod +x "$WARMUP_PROGRAM"

sudo tee /usr/local/bin/nancee-ollama-warmup >/dev/null <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="$VENV/bin:\$PATH"

cd "$ROOT/nancee/sherpa"

exec "$WARMUP_PROGRAM" "\$@"
EOF

sudo chmod 0755 /usr/local/bin/nancee-ollama-warmup


log "Installing the existing warmup service"

sudo install \
    -m 0644 \
    "$WARMUP_SERVICE" \
    /etc/systemd/system/nancee-llm-warmup@.service

sudo mkdir -p \
    /etc/systemd/system/nancee-llm-warmup@.service.d

sudo tee \
    /etc/systemd/system/nancee-llm-warmup@.service.d/override.conf \
    >/dev/null <<EOF
[Service]
User=$INSTALL_USER
Group=$INSTALL_GROUP
WorkingDirectory="$ROOT/nancee/sherpa"
Environment="HOME=$INSTALL_HOME"

ExecStart=
ExecStart=/usr/local/bin/nancee-ollama-warmup %i
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$WARMUP_UNIT"


log "Testing the Ollama warmup service"

if ! sudo systemctl restart "$WARMUP_UNIT"; then
    sudo systemctl status \
        "$WARMUP_UNIT" \
        --no-pager \
        --lines=30 \
        || true

    die "The Ollama warmup service failed."
fi


printf '\nInstallation complete.\n'
printf '\nRun the ICCS Voice Harness with:\n\n'
printf '  cd "%s"\n' "$ROOT"
printf '  source nancee/sherpa/venv/bin/activate\n'
printf '  python3 nancee/sherpa/nancee_chat.py\n\n'
