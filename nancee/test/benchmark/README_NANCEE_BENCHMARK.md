# NANCEE Overnight Benchmark

This benchmark targets the current Raspberry Pi + Ollama + Sherpa Kokoro stack.

## Overnight grid

- LLM temperatures: `0.2, 0.3, 0.4`
- Ollama threads: `3, 4`
- TTS speeds: `1.15, 1.20, 1.25`
- Sherpa threads: `3, 4`
- 12 prompt cases
- 2 repetitions

Total: **864 integrated LLM/TTS runs**.

The benchmark uses the current `system-prompt.txt` and current `tts_chunking.py`. It records token timing, replays the live chunker, synthesizes every chunk, and simulates the one-worker TTS schedule.

## Install

Unzip the bundle, then run:

```bash
cd NANCEE_Overnight_Benchmark_Bundle
./install_benchmark.sh
```

## Smoke test first

```bash
cd ~/Nancee/nancee
source sherpa/venv/bin/activate

python3 test/benchmark/nancee_overnight_benchmark.py \
  --mode quick \
  --save-wavs \
  --output test/benchmark/results-quick
```

Do not start the overnight run until this completes.

## Start overnight

```bash
cd ~/Nancee/nancee
mkdir -p test/benchmark/results

nohup test/benchmark/run_nancee_overnight_benchmark.sh \
  > test/benchmark/results/nohup.out 2>&1 &

echo $! > test/benchmark/results/benchmark.pid
```

Monitor:

```bash
tail -f test/benchmark/results/benchmark.log
```

Check status:

```bash
ps -fp "$(cat test/benchmark/results/benchmark.pid)"
```

Stop:

```bash
kill "$(cat test/benchmark/results/benchmark.pid)"
```

Restart safely:

```bash
test/benchmark/run_nancee_overnight_benchmark.sh
```

`--resume` skips completed run keys.

## Morning outputs

- `results/ranked_configs.csv`
- `results/top_10.json`
- `results/runs.csv`
- `results/raw_results.jsonl`
- `results/wav_samples/`

The automatic rank favors prompt obedience, first-audio latency, P95 first-audio latency, and total turn time. Listen to WAV samples from the top five configurations before choosing the final tuning.

## Pitch and questions

Your current Sherpa Kokoro configuration exposes speed but no direct pitch control. The benchmark saves question WAVs at speeds 1.15, 1.20, and 1.25 so you can judge whether speed changes make question intonation more or less natural.

Do not add DSP pitch shifting yet. It may raise the final pitch, but it often sounds synthetic and does not teach Kokoro proper English question prosody.

## Limitation

The benchmark does not exercise ASR, the physical sound device, initial bridge clips, or mid-response fillers. It benchmarks the core LLM → current chunker → Kokoro path and simulates when each chunk would become audible.
