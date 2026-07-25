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
- **ASR:** OpenAI Whisper English models, currently centered on `whisper-base.en` while alternatives are benchmarked.
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

## What TPC Is

**TPC** stands for **Tenacious Prefix Cache**.

TPC is a small model-runtime gateway that tries to keep the next stable prompt prefix shape before the next real user request reaches the LLM.

Its purpose is to reduce repeated prompt-evaluation work on constrained hardware.

The central idea is simple:

```text
prepare the reusable prompt prefix early
    -> verify that the real request needs that exact prefix
    -> send the real request through the prepared model state
    -> prepare the next completed-turn prefix in the background
```

TPC does not generate an answer ahead of time. It prepares only the stable portion of the prompt that is already known.

## The Problem TPC Solves

A conversational model request usually contains a large amount of text that did not originate with the newest user utterance:

```text
system prompt
+ stable instructions
+ completed conversation history
+ stable memory context
+ new user input
```

Without reuse, the model may repeatedly evaluate the same system prompt and recent conversation before it reaches the only new part: the user's latest input.

On a desktop GPU that cost may be small. On a Raspberry Pi, repeated prompt evaluation can add a noticeable delay before the first response token.

TPC moves as much of that work as possible into idle time between turns.

## What “Stable Prefix” Means

The **stable prefix** is the exact ordered prompt content that appears before the newest request-specific material.

In NANCEE it may include:

- The system prompt.
- Stable behavioral instructions.
- Completed user and assistant messages.
- Memory context that is already known when the prime is scheduled.

It normally does **not** include the new user input because that input does not exist yet when the next prefix is prepared.

The model backend decides how the messages become a concrete prompt. TPC only manages the lifecycle and verifies prompt identity.

## TPC Lifecycle

```text
APPLICATION START
      |
      v
prime_now(...)
Synchronously prepare the startup prefix.
      |
      v
WAIT FOR USER
      |
      v
stream_response(...)
Wait for any pending prime.
Fingerprint the prefix needed now.
Require it to match the prepared fingerprint.
Run the real streaming model request.
Consume the prepared state.
      |
      v
TURN COMPLETES
      |
      v
prime_async(...)
Copy the newly completed history.
Prepare the next prefix on one background worker.
      |
      +---------------------------> WAIT FOR NEXT USER
```

A real model request invalidates the previously prepared state. After the request completes, the caller must schedule the next completed-turn prefix or an appropriate recovery prefix.

## What TPC Actually Owns

TPC owns:

- Startup and background prime scheduling.
- One-worker background execution.
- Waiting for a pending prime before a real request.
- Immutable snapshots of history and memory context.
- SHA-256 prefix identity checks.
- The exact-prefix sanity gate.
- Single-request and single-prime lifecycle protection.
- Publishing whether a prefix is scheduled, prepared, consumed, or unavailable.
- Clean shutdown of the background worker.

TPC does **not** own:

- The model itself.
- Ollama-specific HTTP calls.
- Prompt formatting rules.
- Token generation.
- Conversation routing.
- Memory retrieval.
- Speech recognition or speech synthesis.
- The model runtime's internal KV-cache implementation.

TPC asks a model adapter to perform the actual prime and request. This keeps the TPC algorithm separate from Ollama and makes it possible to adapt the same lifecycle to another runtime.

## Public Integration Contract

`TenaciousPrefixCache` receives three real functions when the object is created:

```python
tpc = TenaciousPrefixCache(
    prime_function=prime_model_prefix,
    request_function=stream_model_response,
    prefix_fingerprint_function=fingerprint_prefix,
)
```

The constructor stores those functions. TPC calls them later when the lifecycle reaches the appropriate stage.

This is dependency injection using ordinary Python functions. The functions are concrete when the TPC object is instantiated, even though the TPC class itself does not know which model runtime they use.

The TPC source intentionally keeps this public contract readable without requiring consumers to understand Python type-hint syntax. The behavior described below is the source of truth.

### 1. `prime_function`

TPC calls the prime function using:

```python
result = prime_function(
    history=history,
    memory_context=memory_context,
)
```

The function must:

- Accept `history` as a named argument.
- Accept `memory_context` as a named argument.
- Perform the model-runtime-specific prefix prime.
- Return a dictionary.
- Include the fingerprint of the prefix it actually prepared under `prefix_sha256`.

Example:

```python
def prime_model_prefix(*, history, memory_context):
    prefix_sha256 = fingerprint_prefix(
        history=history,
        memory_context=memory_context,
    )

    # Runtime-specific prime request happens here.

    return {
        "prefix_sha256": prefix_sha256,
        "elapsed_seconds": 1.42,
    }
```

TPC verifies that the returned fingerprint matches the fingerprint calculated before the prime began.

### 2. `request_function`

TPC calls the request function using:

```python
request_function(
    history=history,
    memory_context=memory_context,
    ...additional request arguments...
)
```

The function must:

- Accept `history` as a named argument.
- Accept `memory_context` as a named argument.
- Accept the additional arguments used by the application.
- Produce response text as an iterable or generator of strings.

Example:

```python
def stream_model_response(
    *,
    history,
    memory_context,
    user_input,
):
    # Runtime-specific streaming request happens here.

    yield "The "
    yield "coolant temperature "
    yield "looks normal."
```

TPC uses `yield from` to pass each response piece directly back to the caller.

### 3. `prefix_fingerprint_function`

TPC calls the fingerprint function using:

```python
prefix_sha256 = prefix_fingerprint_function(
    history=history,
    memory_context=memory_context,
)
```

The function must:

- Accept `history` as a named argument.
- Accept `memory_context` as a named argument.
- Build the same stable prefix representation used by the model runtime.
- Return a repeatable string fingerprint.

The same exact prefix must always produce the same fingerprint. Any meaningful change to message order, text, system instructions, history, or included memory must produce a different fingerprint.

A real implementation should hash a deterministic serialization of the exact stable prompt.

## Meaning of the Shared Inputs

### `history`

`history` is the completed conversation context included in the stable prefix.

Example:

```python
history = [
    {
        "role": "user",
        "content": "My engine ran hot yesterday.",
    },
    {
        "role": "assistant",
        "content": "Did the temperature warning appear?",
    },
]
```

It does not mean all conversation ever recorded. The application decides how much recent history belongs in the prompt.

TPC makes a deep copy of the supplied history before priming or requesting. This prevents another part of the application from changing nested message dictionaries while a background operation is using them.

### `memory_context`

`memory_context` is additional recalled or supplied context that belongs in the stable prompt prefix.

Example:

```text
The user bought a pair of jeans yesterday.
```

Dynamic memory retrieval deserves special care. If recall results are discovered after a different prefix was already prepared, the real prefix fingerprint will change. The application must either prepare the correct context or intentionally allow a non-exact path for that request.

### Additional request arguments

Values that only matter to the real request can pass through `stream_response` as keyword arguments:

```python
for text in tpc.stream_response(
    history=history,
    memory_context=memory_context,
    user_input="What did I buy yesterday?",
    temperature=0.2,
):
    print(text, end="", flush=True)
```

TPC does not interpret those extra values. It forwards them to `request_function`.

## Why TPC Uses One Worker

TPC creates a thread pool with one worker:

```python
ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="nancee-tpc",
)
```

One worker is intentional. TPC should prepare one next prefix, not several competing guesses.

The background thread allows priming to happen while the foreground application is idle or doing unrelated work. The single-worker limit keeps that background path serial and predictable.

The thread name is optional and exists to make debugging, traces, and process inspection easier.

## Why TPC Uses an `RLock`

The reentrant lock protects the small amount of shared state used by the main thread and the background prime thread:

- The pending `Future`.
- The scheduled fingerprint.
- The prepared fingerprint.
- Whether a real request is active.
- Whether TPC has been closed.

The lock does not protect the model's prefix from being modified by the model. It prevents application-side race conditions where two threads inspect or change TPC state at the same time.

The lock is held only while checking or changing TPC bookkeeping. It is deliberately not held for the entire model prime or full streaming response.

## What the `Future` Represents

`self._future` is the handle returned when the one-worker executor accepts a background prime job.

It is not an asynchronous dictionary. It is an object representing work that may still be running.

TPC uses it to ask:

- Does a background prime exist?
- Is it still running?
- Did it finish?
- What result did it return?
- Did it raise an exception?

Calling `future.result()` waits until the prime finishes, returns the prime result, or re-raises the prime exception.

## Exact-Prefix Verification

Before a strict real request begins, TPC compares:

```text
prepared_prefix_sha256
        versus
actual_prefix_sha256 needed by this request
```

A match means the model was primed with the same stable prefix that the real request is about to use.

A mismatch means the prepared work belongs to a different prompt shape or context. In strict mode, TPC raises an error instead of silently claiming a cache hit.

Typical log:

```text
[TPC PREFIX] match=true required=true prepared=<sha256> actual=<sha256>
```

Possible causes of a mismatch include:

- Conversation history changed after the prime was scheduled.
- Dynamic recall added different memory context.
- The system prompt changed.
- Message formatting or ordering changed.
- The prime path and request path built the prefix differently.
- The wrong prepared prefix was published.

The fingerprint is a correctness gate. It does not prove that the backend actually reused internal cached computation, but it proves that the application requested and prepared the same prefix.

## Synchronous and Asynchronous Prime Methods

### `prime_now(...)`

Used when the application cannot continue safely without a prepared prefix, normally at startup or during recovery.

It runs in the current thread and blocks until the prime succeeds or fails.

### `prime_async(...)`

Used after a completed turn when the next stable conversation prefix is already known.

It copies the completed state and submits one prime job to the background worker.

### `wait_until_ready()`

Used before the next real request. It waits only when a scheduled prime has not finished yet.

### `stream_response(...)`

The supported gateway for a real streaming request. It:

1. Finishes any pending prime.
2. Copies the request state.
3. Calculates the exact prefix needed now.
4. Verifies the prepared fingerprint.
5. Marks a real request active.
6. Consumes the prepared state.
7. Streams model text.
8. Clears the active-request flag even when an exception occurs.

### `shutdown()`

Waits for pending preparation, marks the object closed, and shuts down the worker exactly once.

## Minimal Runtime-Neutral Example

This example demonstrates the public shape without depending on Ollama:

```python
import hashlib
import json

from tenacious_prefix_cache import TenaciousPrefixCache


def stable_prefix_data(*, history, memory_context):
    return {
        "system": "You are a concise local assistant.",
        "history": history,
        "memory_context": memory_context,
    }


def fingerprint_prefix(*, history, memory_context):
    serialized = json.dumps(
        stable_prefix_data(
            history=history,
            memory_context=memory_context,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def prime_model_prefix(*, history, memory_context):
    prefix_sha256 = fingerprint_prefix(
        history=history,
        memory_context=memory_context,
    )

    # Send a harmless runtime-specific request here to prepare the prefix.

    return {
        "prefix_sha256": prefix_sha256,
    }


def stream_model_response(
    *,
    history,
    memory_context,
    user_input,
):
    # Send the real runtime-specific request here.

    yield f"Example response to: {user_input}"


tpc = TenaciousPrefixCache(
    prime_function=prime_model_prefix,
    request_function=stream_model_response,
    prefix_fingerprint_function=fingerprint_prefix,
)

history = []
memory_context = ""

tpc.prime_now(
    history=history,
    memory_context=memory_context,
    reason="startup",
)

for piece in tpc.stream_response(
    history=history,
    memory_context=memory_context,
    user_input="Hello",
):
    print(piece, end="", flush=True)

completed_history = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Example response to: Hello"},
]

tpc.prime_async(
    history=completed_history,
    memory_context="",
    reason="completed_turn",
)

tpc.shutdown()
```

## Adapting TPC to Another Model Runtime

A contributor does not need to rewrite the TPC lifecycle. The contributor needs to provide an adapter with three matching behaviors:

1. Build and prime the backend's stable prompt prefix.
2. Stream a real response using the same prompt construction.
3. Calculate a deterministic fingerprint from that same stable prefix.

The most important rule is that the prime path, fingerprint path, and real request path must agree on the exact prefix representation.

A backend is a good TPC candidate when it can benefit from repeated identical prompt prefixes or persistent model context. A backend that discards all prompt state after every call may still work correctly through TPC but will not receive the intended performance benefit.

## TPC Performance

TPC was retained because controlled NANCEE benchmarks showed a repeatable reduction in median first-token latency and prompt-evaluation time on the Raspberry Pi. The improvement came primarily from prompt evaluation rather than router execution or thread scheduling.

Performance is workload-dependent. Exact gains will change with:

- Model size and quantization.
- Prompt length.
- Backend caching behavior.
- Conversation-history length.
- Dynamic memory context.
- CPU frequency, temperature, and throttling.

TPC should be benchmarked against an equivalent no-TPC path on each supported backend. Correctness must be verified before latency improvements are trusted.

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
- Keep model behavior separate from safety-critical control.
- Prefer simple local components when they solve the problem well.
- Preserve a conversational presence without hiding incorrect behavior.
- Treat constrained hardware as an architecture problem, not merely a limitation.

The project is experimental, but the experiments should remain reproducible, testable, and honest.
