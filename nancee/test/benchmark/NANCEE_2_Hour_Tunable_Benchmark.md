# NANCEE Two-Hour Tunable Benchmark

## Purpose

This benchmark compares runtime tunables for the current `phi4-mini:3.8b` build without changing the model or architecture.

Primary goals, in order:

1. No invented personal facts or shared experiences.
2. Correct episodic and profile recall.
3. Correct `you/your` perspective before TTS.
4. Complete thoughts with no token-limit fragments.
5. Natural, read-the-room responses.
6. Minimal unnecessary bridge/filler speech.
7. Good latency after the quality requirements are satisfied.

Do **not** mix this benchmark with tomorrow's model comparison. Tonight is for tunables only.

## What the latest log says

The current architecture is substantially better:

- Episodic facts are stored.
- FTS recall is working.
- Perspective repair converts `I finished...` to `You finished...`.
- Profile validation protects the name response.
- The response policy cuts down chatter.

The current weak points are:

- `normal num_predict=36` can end a response mid-thought.
- A wrong factual answer can contaminate the next one-turn history.
- Initial bridge phrases still fire on many short answers.
- Small-model knowledge errors must be scored separately from personal-memory hallucinations.

The Sauron run contained both a **knowledge error** and a **length cutoff**. Morgoth was Sauron's master, but the response also ended because `reason=length`. Treat those as two different failures.

---

# Frozen settings

Keep these unchanged for the entire two-hour run:

- Model: `phi4-mini:3.8b`
- Ollama threads: 4
- TTS threads: 3
- TTS speed: 1.25
- Acknowledgement: 18 tokens, temperature 0.25
- Recall: 18 tokens or the profile-specific value below
- Recent prompt turns: 1
- FTS memory limit and retrieval settings
- System prompt
- All code
- Microphone position and speaking volume

Restart `nancee_chat.py` between every profile so each profile begins with:

```text
recall_turns=0
```

---

# Quality profiles

## Profile A — Current baseline

```text
normal:   temperature 0.30, num_predict 36
detailed: temperature 0.30, num_predict 65
recall:   temperature 0.15, num_predict 18
```

Expected behavior: fastest and most expressive, but most likely to truncate or improvise.

## Profile B — Grounded and complete

```text
normal:   temperature 0.20, num_predict 48
detailed: temperature 0.20, num_predict 80
recall:   temperature 0.10, num_predict 18
```

Expected behavior: safest and most complete, but possibly dry or repetitive.

## Profile C — Balanced

```text
normal:   temperature 0.25, num_predict 44
detailed: temperature 0.25, num_predict 72
recall:   temperature 0.12, num_predict 18
```

Expected behavior: likely best overall balance.

During the quality phase, disable the initial latency bridge. That prevents filler timing from influencing judgments about the model's actual response.

---

# Two-hour schedule

## 0:00–0:10 — Setup

1. Commit the current clean-and-green code.
2. Create the log directory.
3. Install the launcher and summary helper from this benchmark pack.
4. Confirm all three quality profiles print the intended values.
5. Do not alter code after the benchmark begins.

## 0:10–0:30 — Profile A

Run the complete 14-prompt quality suite.

## 0:30–0:50 — Profile B

Restart NANCEE and run the exact same 14 prompts.

## 0:50–1:10 — Profile C

Restart NANCEE and run the exact same 14 prompts.

## 1:10–1:20 — Score quality

Reject any profile that violates a hard-fail rule. Choose the best remaining profile.

## 1:20–1:30 — Bridge profile 1

Use the winning quality profile with:

```text
normal bridge: 6.3 seconds
recall bridge: 5.2 seconds
```

Run the bridge micro-suite.

## 1:30–1:40 — Bridge profile 2

Use:

```text
normal bridge: 6.8 seconds
recall bridge: 5.8 seconds
```

Run the same bridge micro-suite.

## 1:40–1:50 — Bridge profile 3

Use:

```text
normal bridge: 7.3 seconds
recall bridge: 6.3 seconds
```

Run the same bridge micro-suite.

## 1:50–2:00 — Final integrated run

Use the winning quality and bridge profiles together. Run the final eight-prompt suite and confirm no regression.

---

# Fourteen-prompt quality suite

Speak these exactly. Do not ad-lib during Profiles A, B, and C.

## Memory seed and read-the-room behavior

1. `Hey Nancee, I bought a green duffel bag at Target today.`

Expected:
- policy `acknowledge`
- brief natural response
- no follow-up
- `MEMORY RAW ADD`
- `recall_turns=1`

2. `I finished soldering a CAN transceiver yesterday.`

Expected:
- policy `acknowledge`
- `MEMORY RAW ADD`
- `recall_turns=2`

3. `What is my name?`

Expected:
- `Your name is Anders.`
- no extra commentary
- no guessed alternate name

4. `What did I buy at Target?`

Expected:
- green duffel bag
- answer uses `you`, not `I`
- recall hit
- no second fact

5. `What did I finish soldering?`

Expected:
- CAN transceiver
- answer uses `you`, not `I`
- recall hit

6. `What is my sister's middle name?`

Expected:
- a short memory miss
- no guessed name
- no privacy explanation
- no apology paragraph

## Correction and conflict handling

7. `Actually, the duffel bag was blue, not green.`

Expected:
- brief acknowledgement
- stored as a newer correction

8. `What color was the duffel bag?`

Expected:
- blue
- newest explicit correction wins

9. `Did you buy the duffel bag, or did I?`

Expected:
- the user bought it
- spoken answer uses `you`
- Nancee does not claim ownership

## General response quality

10. `What is the capital of France?`

Expected:
- direct one-sentence answer
- no bridge during the quality phase
- no follow-up

11. `Explain in two sentences how a turbocharger works.`

Expected:
- exactly one or two complete sentences
- no sentence fragment
- no `reason=length`
- mechanically coherent

12. `Give me a brief history of Sauron and state his relationship to Morgoth.`

Expected factual core:
- Sauron was originally a Maia
- he became a servant or lieutenant of Morgoth
- he later became the principal Dark Lord after Morgoth's defeat

Score factual correctness separately from personal-memory grounding.

13. `Morgoth was Sauron's master, right?`

Expected:
- yes, with a concise correction or confirmation
- no invented reversal
- no continuation from a truncated prior answer

14. `Hardly drive.`

Expected:
- asks for clarification
- does not invent a driving scenario
- does not store the fragment

---

# Bridge micro-suite

Restart NANCEE for every bridge profile.

1. `I bought a yellow notebook at Staples today.`
2. `Hello Nancee, how are you?`
3. `What is the capital of France?`
4. `What is my name?`
5. `What did I buy at Staples?`
6. `I finally finished a difficult solder job.`
7. `Explain in two sentences what an intercooler does.`

For each turn record:

- Did the bridge fire?
- Did it overlap or feel redundant?
- Did the real answer arrive within roughly one second after the bridge?
- Would silence have sounded better?
- Did a recall answer get a pointless phrase such as “Let me check that”?

Choose the lowest threshold pair that does **not** routinely overlap short answers.

---

# Final integrated suite

Use the winning quality and bridge settings.

1. `Hey Nancee, I replaced a wheel-speed sensor today.`
2. `I bought a black flashlight at Home Depot yesterday.`
3. `What did I replace today?`
4. `What did I buy yesterday?`
5. `Did you buy it, or did I?`
6. `What is my wife's name?`
7. `Explain briefly why an engine intercooler lowers knock risk.`
8. `Tell me the relationship between Morgoth and Sauron in one sentence.`

The build is ready for the overnight benchmark only if all eight are acceptable.

---

# Scoring

Score every quality-suite turn from 0 to 10.

## Grounding and correctness — 0 to 3

- 3: Fully grounded or factually correct.
- 2: Essentially correct with harmless wording.
- 1: Partially wrong or vague.
- 0: Invented personal fact, reversed relationship, or unrelated answer.

## Complete thought — 0 to 2

- 2: Complete sentence or naturally complete short response.
- 1: Awkward but complete.
- 0: Ends mid-sentence, dangling parenthesis, or `reason=length` fragment.

## Naturalness and read-the-room behavior — 0 to 2

- 2: Sounds like a natural passenger response.
- 1: Stiff, generic, or slightly overdone.
- 0: Customer-service voice, lecture, or bizarre interpretation.

## Memory and perspective — 0 to 2

- 2: Correct retrieval and correct `you/your` perspective.
- 1: Correct fact but awkward perspective repaired only after a visible model miss.
- 0: Wrong memory, missed stored fact, or wrong perspective reaches TTS.

For non-memory turns, award 2 unless memory contamination appears.

## Chatter discipline — 0 to 1

- 1: Stops when the answer is complete.
- 0: Adds an unnecessary question, advice, story, or closing.

Maximum per quality profile:

```text
14 prompts × 10 points = 140 points
```

---

# Hard-fail rules

Reject a quality profile regardless of its numeric total if any of these occur:

- Any invented personal memory reaches TTS.
- Any wrong `I/me/my` perspective reaches TTS on a retrieved user fact.
- More than one stored fact is missed by FTS recall.
- An unknown personal fact is guessed.
- More than two answers end with `reason=length`.
- A correction question repeats a known factual reversal after the user corrects it.
- A fragment such as `Hardly drive.` is stored as memory.

---

# Selection rule

1. Remove hard-failed profiles.
2. Among the remaining profiles, compare:
   - memory/perspective score first
   - grounding/correctness second
   - completeness third
   - naturalness fourth
3. Use latency only as a tiebreaker.
4. Tune bridge thresholds only after choosing the response-quality profile.

A slower grounded answer is better than a fast hallucination.

---

# Log capture

Use the supplied launcher:

```bash
chmod +x nancee_bench_profile.sh

./nancee_bench_profile.sh A off
./nancee_bench_profile.sh B off
./nancee_bench_profile.sh C off
```

After choosing the quality winner, for example `C`:

```bash
./nancee_bench_profile.sh C 1
./nancee_bench_profile.sh C 2
./nancee_bench_profile.sh C 3
```

Summarize a log:

```bash
python3 nancee_bench_summary.py benchmark_logs/<log-file>.log
```

Useful raw grep:

```bash
grep -E \
'\[RESPONSE POLICY\]|\[LLM FIRST TOKEN\]|\[OLLAMA DONE\]|\[LATENCY BRIDGE\] fired|\[MEMORY RAW (ADD|SKIP)\]|\[MEMORY RECALL\]|\[MEMORY PERSPECTIVE REPAIR\]|\[AUTHORITATIVE RESPONSE GUARD\]|\[TURN DONE\]' \
benchmark_logs/<log-file>.log
```

---

# What not to tune tonight

Keep these fixed so the results remain interpretable:

- Ollama thread count
- TTS thread count
- TTS speed
- chunk sizes
- memory index limits
- FTS scoring
- system prompt
- model
- ASR model
- recent-history window

Those belong in separate benchmarks.

---

# Likely outcome

Based on the current log:

- Profile A will probably remain the fastest but lose points for truncation and factual improvisation.
- Profile B will probably be safest but may feel dry.
- Profile C is the most likely overall winner.
- Bridge profile 2 is the most likely timing winner.

Do not adopt that prediction without scoring the runs.
