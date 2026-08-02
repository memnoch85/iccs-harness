# NANCEE ICCS Voice Harness

NANCEE is a local, CPU-only voice-assistant harness for demonstrating **Iterative Cache Control and Shaping (ICCS)** on a Raspberry Pi 5. It keeps speech recognition, language-model inference, memory retrieval, text-to-speech, routing, and cache-shaping logic on the device.

This repository is intentionally narrower than the private NANCEE vehicle project. It does not include CAN/OBD communication, a vehicle database, static user profiles, or conversational speaker switching.

## Runtime stack

- Raspberry Pi 5, 8 GB RAM
- Ollama with Llama 3.2 3B
- Faster-Whisper `base.en`, CPU INT8, four threads, beam size 1
- Kokoro ONNX through Sherpa ONNX, 24 kHz, voice ID 3
- PipeWire/WirePlumber audio through `sounddevice`
- One completed user/assistant turn in the active prompt
- In-memory SQLite FTS5 for selective session recall
- ICCS for exact stable-prefix shaping, priming, verification, and reuse

The removed `nancee/db` directory belonged to the old vehicle-data architecture. Session recall still uses SQLite FTS5, but creates its small FTS5 table directly in memory inside `session_memory_store.py`; it does not use `create_tables.sql` or `init_db.sh`.

## Turn pipeline

```text
microphone
    -> Faster-Whisper transcription
    -> input routing
    -> optional FTS5 session recall
    -> ICCS exact-prefix verification
    -> Ollama streaming response
    -> semantic text chunking
    -> Kokoro speech synthesis
    -> PipeWire output
```

## ICCS

ICCS is an application strategy layered above the inference runtime's automatic prefix caching. It does not create or control the runtime's internal KV cache. It deliberately presents the runtime with the same reusable beginning and measures the resulting prompt-evaluation behavior.

For completed turn `n`:

```text
B   = stable system prompt
D_n = U_n + A_n, the latest completed turn
P_n = B + D_n, the next reusable stable prefix
k   = one disposable lowercase priming response
I   = optional current-turn retrieval or route guidance
```

Startup synchronously primes `B`. After every completed turn, ICCS freezes and fingerprints `P_n`, then primes it asynchronously while the answer is being spoken and while the user prepares the next request. At the next request, ICCS rebuilds the expected prefix, compares its SHA-256 identity with the prepared snapshot, and either consumes the exact prepared shape or safely uses a fresh dynamic shape when exact matching is not required.

A normal request adds no route instruction:

```text
R_(n+1) = B + U_n + A_n + U_(n+1)
```

Only genuinely current-turn material is appended dynamically:

```text
R_(n+1) = B + U_n + A_n + I_(n+1) + U_(n+1)
```

The prime instruction and generated `k` are disposable. They are not stored in conversation history and are not part of the next stable prefix.

## Important files

```text
nancee/
├── asr/
│   ├── asr_worker.py
│   └── transcribe.py
├── sherpa/
│   ├── iccs.py
│   ├── nancee_chat.py
│   ├── ollama_runtime.py
│   ├── prompt_contract.py
│   ├── warmup_contract.py
│   ├── input_router.py
│   ├── response_policy.py
│   ├── session_memory_store.py
│   ├── session_archive.py
│   ├── latency_bridge.py
│   └── system-prompt.txt
└── test/
    ├── run_unit_tests.sh
    └── unit/
```

## Run NANCEE

```bash
cd "$HOME/iccs-harness" || exit 1
python3 nancee/sherpa/nancee_chat.py
```

A correct live run reports only ICCS lifecycle markers:

```text
[ICCS PRIME]
[ICCS PREFIX]
```

No legacy cache-controller lifecycle markers should appear.

## Run unit tests

```bash
cd "$HOME/iccs-harness" || exit 1
nancee/test/run_unit_tests.sh
```

Verbose mode:

```bash
nancee/test/run_unit_tests.sh -v
```

## Scope

The public harness demonstrates a complete local voice loop, bounded prompt history, selective FTS5 recall, routing, response policies, latency bridges, and ICCS. Hardware vehicle communication and persistent vehicle tables are deliberately outside this repository.

## Accuracy boundary

The application SHA-256 proves that the prepared and reconstructed message prefixes are identical under the harness's canonical serialization. It does not expose Ollama's internal KV tensors and does not independently prove a backend cache hit. Reduced prompt-evaluation time under matched-prefix controls is the behavioral evidence.
