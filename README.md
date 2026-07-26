# NANCEE

**NANCEE** is an experimental, local-first voice assistant designed for constrained edge hardware and vehicle diagnostics.

The current proof of concept runs on a Raspberry Pi 5 and keeps the speech, language model, memory, and most control logic on the device. The project is deliberately focused on reducing latency and getting useful AI behavior from modest hardware instead of treating a cloud API as the default architecture.

> **Project status:** active proof of concept. The architecture changes frequently. This README describes the current direction and is not a promise that every file name or command will remain stable.

## Current Direction

The original NANCEE plan centered on an Android phone, Bluetooth OBD adapter, and Kotlin application. The project has since moved toward a dedicated Raspberry Pi edge-compute platform with local ASR, LLM, TTS, memory, and CAN access.

Current goals:

- Natural local voice conversation in a vehicle.
- Useful response times on constrained hardware.
- Local speech recognition and speech synthesis.
- Local conversation memory and indexed recall.
- Read-only OBD-II and CAN diagnostics during the proof of concept.
- A model runtime that remains useful without a required cloud connection.
- Algorithms that reduce perceived and actual response latency.

## Current Proof-of-Concept Stack

The exact models and settings are still being benchmarked, but the current working stack is approximately:

- **Compute:** Raspberry Pi 5, 8 GB RAM, NVMe storage.
- **LLM runtime:** Ollama with a small local instruct model.
- **Current LLM family:** Llama 3.2 3B.
- **ASR:** Faster-Whisper using the OpenAI Whisper `base.en` model via CTranslate2, with INT8 compute, 4 CPU threads, beam size 1, and VAD filtering disabled.
- **TTS:** Kokoro ONNX at 24 kHz.
- **Memory:** SQLite with FTS5 full-text retrieval.
- **Vehicle communication:** SocketCAN with MCP2515 and CANable interfaces.
- **Application language:** Python for the current integrated runtime.

NANCEE is not just a chain of model calls. The runtime also contains routing, response policy, prompt identity checks, memory retrieval, streaming text segmentation, latency bridges, audio coordination, and model warmup behavior.

## High-Level Turn Pipeline

A normal spoken turn follows this general path:

```text
microphone
    -> speech recording
    -> Whisper transcription
    -> input routing
    -> optional FTS5 memory recall
    -> TPC exact-prefix gateway
    -> local LLM streaming response
    -> semantic text chunking
    -> Kokoro speech synthesis
    -> speaker output
```

Several stages overlap when safe. For example, completed conversation state can be primed in the background while the user prepares the next request.

## Running the Current Chat Runtime

From the project root:

```bash
cd "$HOME/Nancee" || exit 1
python3 nancee/sherpa/nancee_chat.py
```

The exact virtual environment and service setup may differ between installations. Configuration is primarily controlled by the project configuration modules and `NANCEE_*` environment variables.

## Approximate Repository Layout

This is a conceptual map rather than a guaranteed complete file listing:

```text
Nancee/
├── README.md
└── nancee/
    ├── sherpa/
    │   ├── nancee_chat.py
    │   ├── tenacious_prefix_cache.py
    │   ├── ollama_runtime.py
    │   ├── config.py
    │   ├── system-prompt.txt
    │   └── ...audio, routing, response, and runtime modules...
    ├── asr/
    │   └── ...Whisper environments and benchmark tools...
    ├── db/
    │   └── nancee.db
    ├── test/
    │   └── ...unit and integration tests...
    └── ...CAN, memory, utilities, and experimental code...
```

The repository contains substantially more code than the original Android-era project plan. A future cleanup should generate this tree directly from the repository instead of maintaining it by hand.

# Tenacious Prefix Cache — TPC

**TPC** stands for **Tenacious Prefix Cache**.

TPC reduces repeated prompt-evaluation work by preparing the next stable conversation prefix during the idle time between user turns.

The basic recurrence is:

```text
B   = fixed base prompt
D_n = new user input
A_n = model answer
S_n = prepared prompt state after turn n

+ means append in exact prompt order
```

```text
S_0 = B
prime(S_0)

A_n = model(S_(n-1) + D_n)
S_n = S_(n-1) + D_n + A_n
prime(S_n)
```

In plain English:

```text
use the already-prepared conversation state
+ add the new user input
+ generate the answer
+ append the completed turn
+ prepare that new state before the next question arrives
```

The useful part is not merely caching. TPC uses otherwise wasted human conversation time the period while the user is listening, thinking, or preparing the next question to perform work that the model would otherwise repeat after the next request.

This became especially attractive after NANCEE's FTS5 memory work made local recall extremely fast. The lookup could still happen when a new request arrived without consuming most of the time saved by background priming. That made TPC a relatively low hanging optimization:

```text
fast FTS5 lookup
+ already-primed stable prefix
+ only the new request left to evaluate
```

TPC also verifies the prepared prefix with a deterministic SHA-256 fingerprint. If history, memory context, message order, or prompt construction changes, the fingerprints no longer match and NANCEE does not falsely treat the old prime as valid.

TPC does not predict the next question or answer, and it does not own the model runtime's internal KV cache. It only manages when a known prompt prefix is prepared, checks that the real request needs the same prefix, and schedules the next completed-turn prime.

Controlled NANCEE benchmarks showed that the main gain came from reduced prompt-evaluation time, not from the router or thread scheduling. The algorithm is small, but it is a useful example of improving edge-model latency by arranging work around idle time instead of demanding larger hardware.

# Memory

NANCEE currently uses a deliberately small live conversation window plus indexed local recall.

The general design is:

```text
recent completed turn
+ FTS5 indexed memories
+ top relevant recall results
```

SQLite FTS5 provides fast lexical retrieval without requiring a separate vector database service. The memory system and TPC interact because recalled context can become part of the model prefix.

# Latency Bridges

TPC reduces actual model work. Latency bridges address a different problem: long audible silence.

The runtime can play short pre-generated filler audio when transcription, routing, model generation, or TTS preparation exceeds a configured silence deadline.

The bridge does not make the model faster and should not be confused with TPC. It protects the conversational experience while slower work continues.

# Vehicle and Safety Scope

The proof of concept is centered on local diagnostics and observation.

Current safety direction:

- Prefer read-only vehicle data.
- Do not present guessed vehicle state as measured data.
- Do not perform control or write operations merely because an LLM requested them.
- Keep driver interaction short and voice-first.
- Treat diagnostic explanations as assistance, not as a substitute for service documentation or professional inspection.

# Testing

From the Python project directory:

```bash
cd "$HOME/Nancee/nancee" || exit 1
python3 -m unittest discover -s test -p 'test_*.py'
```

Compile-check a modified Python module before running the full suite:

```bash
python3 -m py_compile sherpa/tenacious_prefix_cache.py
```

TPC tests should cover at least:

- Successful synchronous startup prime.
- Successful background prime.
- Waiting for an incomplete `Future`.
- Publishing a completed prepared fingerprint.
- Exact-prefix success.
- Exact-prefix mismatch failure.
- Refusing two active real requests.
- Refusing overlapping prime jobs.
- Recovery after a prime exception.
- Shutdown with and without pending work.

# Known Work in Progress

- Continued ASR model and backend benchmarking.
- Voice and speaker recognition beyond conversational guesses.
- Name normalization for ASR variants of “Nancee.”
- TTS latency and chunking improvements.
- Stable in-vehicle power control and enclosure design.
- More complete CAN and OBD diagnostic tooling.
- Repository cleanup and documentation generated from the actual source tree.
- Packaging and installation suitable for contributors who do not share the original development machine.

# Project Philosophy

NANCEE is built around a few strong preferences:

- Local-first rather than cloud-required.
- Measure latency instead of guessing.
- Use classical computer-science techniques before demanding larger hardware.
- Keep model behavior separate from critical control.
- Prefer simple local components when they solve the problem well.
- Preserve a conversational presence without hiding incorrect behavior.
- Treat constrained hardware as an architecture problem, not merely a limitation.

The project is experimental, but the experiments should remain reproducible, testable, and honest.
