# ICCS Voice Harness

A local, CPU-only voice-assistant harness for demonstrating Iterative Cache Control and Shaping (ICCS) on a Raspberry Pi 5. This project demonstrates how ICCS, FTS5 session memory, and response routing can keep latency stable and predictable across long-running conversations.

At present the model only evaulates  user supplied input for memory, as I am still deciding on the best routing approach

New here? Start with [What is ICCS?](https://github.com/memnoch85/iccs).

If you want to install it and run it start below. 

## ICCS Voice Harness Demo

[![Watch the ICCS Voice Harness demo](https://img.youtube.com/vi/9CTAGkp46Pk/hqdefault.jpg)](https://youtu.be/9CTAGkp46Pk)

**[Watch the 9-minute proof-of-concept demo on YouTube](https://youtu.be/9CTAGkp46Pk).**


## Why ICCS?
*Give a small model less to process—and more of the right context.*

1. **Small models need focused instructions.**  
   Models that fit comfortably on a Raspberry Pi 5 can handle immediate tasks well, but they are less reliable when asked to interpret long prompts, follow many conditional rules, and determine their own routing. ICCS helps turn each request into a smaller, clearer problem.

2. **Targeted retrieval beats prompt stuffing.**  
   SQLite FTS5 can retrieve a few relevant memories instead of making the model reread an entire conversation. This reduces prompt processing work and can make factual recall more reliable.

3. **Because I don't want to buy any more damn hardware.**  
   Accelerators can help especially with prompt processing but they also add cost, power use, heat, and platform constraints.

4. **Local should actually mean local.**  
   I do not want the final product to feel like an API client for another computer or company.

5. **Predictable performance matters.**  
   ICCS aims to make small-model behavior and latency more reproducible by controlling prompt shape, routing, and retrieved context instead of relying on a large, variable context window.

ICCS does not make a small model smarter. It reduces repeated prompt work, supplies more relevant context, and gives the model a better chance to use the intelligence it already has.

> **Note:** This harness is an early proof of concept; its design may change as the solution matures, and older model-turn recall is not yet indexed in FTS5.



## Tested Hardware / Configuration

- **Computer:** Raspberry Pi 5 Model B Rev 1.1, 8 GB RAM
- **Storage:** Fanxiang S501 128 GB NVMe SSD
- **Cooling:** Active cooling
- **Operation:** Headless, with no display manager or desktop environment
- **CPU:** `performance` governor, 2.4 GHz maximum frequency
- **OS:** Debian 13.5 (`trixie`), 64-bit ARM
- **Kernel:** Linux `6.18.29+rpt-rpi-2712`, `aarch64`
- **Audio:** PipeWire 1.4.2, `pipewire-pulse` 1.4.2,
  `pipewire-alsa` 1.4.2, and WirePlumber 0.5.8
- **Python:** 3.13.5
- **LLM:** Ollama 0.31.1 with `llama3.2:3b`
- **ASR:** Faster-Whisper 1.2.1 with CTranslate2 4.8.1,
  `base.en`, CPU INT8, four threads, beam size 1, 16 kHz input
- **TTS:** Kokoro multi-language v1.0 through Sherpa ONNX 1.13.4,
  voice ID 3, 24 kHz output, three CPU threads
- **Runtime libraries:** NumPy 2.2.6 and sounddevice 0.5.5
- **Recall:** In-memory SQLite 3.46.1 with FTS5 enabled

### Key Runtime Settings

| Setting | Value | Meaning |
|---|---:|---|
| `BLOCKSIZE` | `1024` | Audio frames per output callback |
| `NANCEE_ASR_THREADS` | `4` | Whisper CPU inference threads |
| `NANCEE_ASR_SAMPLE_RATE` | `16000` | 16 kHz microphone input |
| `NANCEE_LLM_NUM_THREADS` | `3` | Ollama LLM CPU inference threads |
| `SHERPA_THREADS` | `3` | Kokoro CPU inference threads |
| `TTS_MAX_NUM_SENTENCES` | `1` | One sentence per synthesis batch |
| `TTS_SILENCE_SCALE` | `0.2` | Reduces generated pause duration |

This guide installs the ICCS Voice Harness on a Raspberry Pi 5.

## 1. Confirm PipeWire

Install the required audio packages:

```bash
sudo apt update
sudo apt install -y \
    pipewire \
    pipewire-pulse \
    wireplumber \
    libspa-0.2-bluetooth
```

Confirm that the required PipeWire services are active:
Note: if you have remnants of pulse audio drivers it will likely cause issues.
```bash
systemctl --user is-active \
    pipewire \
    pipewire-pulse \
    wireplumber
```

Expected:

```text
active
active
active
```

PulseAudio is not part of the tested configuration and is not guaranteed to work correctly with this harness.

## 2. Hardware Performance Considerations

Reproducing the tested response times required benchmarking several hardware and software configurations. The most important hardware choices were:

- using the CPU `performance` governor;
- running from an NVMe SSD;
- using active cooling;
- running headless without a desktop environment.

Overclocking was tested but found to increase heat and worsen response latency. The tested configuration uses the Raspberry Pi 5's normal 2.4 GHz maximum frequency.

### Set the CPU Governor to Performance

Create a persistent systemd service:

```bash
sudo tee /etc/systemd/system/cpu-performance-governor.service >/dev/null <<'EOF'
[Unit]
Description=Set CPU governor to performance
After=systemd-modules-load.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'for file in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do echo performance > "$file"; done'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
```

Enable the performance governor immediately and at boot:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cpu-performance-governor.service
```

Verify it:

```bash
cat /sys/devices/system/cpu/cpufreq/policy*/scaling_governor \
    | sort -u
```

Expected:

```text
performance
```

## 3. Clone and Install

```bash
git clone git@github.com:memnoch85/iccs-harness.git iccs-harness
cd iccs-harness

chmod +x setup.sh
./setup.sh
```

The installer:

- installs the required system and Python packages;
- installs Ollama and downloads `llama3.2:3b`;
- creates the required Python environment;
- downloads Faster-Whisper `base.en`;
- downloads the Kokoro ONNX voice model;
- installs and enables the repository's existing Ollama warmup service;
- runs the unit tests.

The first installation may download several gigabytes and can take a while.

## 4. Run Unit Tests

```bash
bash nancee/test/run_unit_tests.sh
```

A successful run ends with output similar to:

```text
----------------------------------------------------------------------
Ran 252 tests in 0.310s

OK
```

If tests fail, the harness may not run correctly.

## 5. Run the Voice Harness

```bash
source nancee/sherpa/venv/bin/activate
python3 nancee/sherpa/nancee_chat.py
```

Press Enter to begin recording, speak, and press Enter again to stop.

Press `Ctrl+C` to exit.
