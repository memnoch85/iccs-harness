# NANCEE ICCS Voice Harness — Installation

This guide installs the NANCEE ICCS voice harness on a Raspberry Pi 5.

## 1. Confirm PipeWire

Install the required audio packages:

```bash
sudo apt update
sudo apt install -y \
    pipewire \
    pipewire-pulse \
    wireplumber \
    libspa-0.2-bluetooth \
```

## 2. Clone and install

```bash
git clonegit@github.com:memnoch85/iccs-harness.git iccs-harness

chmod +x setup.sh
./setup.sh
```

The installer:

- installs the required system and Python packages;
- installs Ollama and downloads `llama3.2:3b`;
- creates one shared Python virtual environment;
- downloads Faster-Whisper `base.en`;
- downloads the Kokoro ONNX voice model;
- installs and enables the repository's existing Ollama warmup service;
- runs the unit tests.

The first installation downloads several gigabytes and can take a while.

## 3. Run NANCEE

```bash
cd "$HOME/iccs-harness" || exit 1
source nancee/sherpa/venv/bin/activate
python3 nancee/sherpa/nancee_chat.py
```

Press Enter to begin recording, speak, and press Enter again to stop.

Press `Ctrl+C` to exit.

## Unit tests

```bash
cd "$HOME/iccs-harness" || exit 1
bash nancee/test/run_unit_tests.sh
```
