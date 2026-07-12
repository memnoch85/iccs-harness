#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import sherpa_onnx

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path.home() / "Nancee" / "nancee"
SHERPA_DIR = REPO_ROOT / "sherpa"
sys.path.insert(0, str(SHERPA_DIR))

from config import (  # noqa: E402
    LLM_MODEL,
    MODEL_DIR,
    OLLAMA_URL,
    SYSTEM_PROMPT_FILE,
    TTS_MAX_NUM_SENTENCES,
    TTS_SILENCE_SCALE,
    VOICE_ID,
)
from tts_chunking import extract_tts_chunk, is_punctuation_only  # noqa: E402


@dataclass(frozen=True)
class BenchConfig:
    temperature: float
    llm_threads: int
    tts_speed: float
    tts_threads: int


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("quick", "overnight", "insane"), default="overnight")
    p.add_argument("--cases", type=Path, default=SCRIPT_DIR / "benchmark_cases.json")
    p.add_argument("--output", type=Path, default=SCRIPT_DIR / "results")
    p.add_argument("--model", default=LLM_MODEL)
    p.add_argument("--repetitions", type=int)
    p.add_argument("--save-wavs", action="store_true")
    p.add_argument("--resume", action="store_true")
    return p.parse_args()


def grid(mode):
    if mode == "quick":
        values = ([0.3], [3], [1.2], [4], 1)
    elif mode == "overnight":
        values = ([0.2, 0.3, 0.4], [3, 4], [1.15, 1.2, 1.25], [3, 4], 2)
    else:
        values = ([0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5], [2, 3, 4], [1.1, 1.15, 1.2, 1.25, 1.3], [3, 4], 3)
    temps, llm_threads, speeds, tts_threads, reps = values
    configs = [BenchConfig(*x) for x in itertools.product(temps, llm_threads, speeds, tts_threads)]
    return configs, reps


def messages_for(system_prompt, case):
    messages = [{"role": "system", "content": system_prompt}]
    memory = str(case.get("memory_context", "")).strip()
    if memory:
        messages.append({
            "role": "system",
            "content": "Use the relevant user memory below. I/me/my in memory refer to the human user; answer as you/your. Do not guess.\n\n" + memory,
        })
    messages.append({"role": "user", "content": case["prompt"]})
    return messages


def stream_ollama(model, messages, temperature, threads):
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature, "num_thread": threads, "num_predict": 65},
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    pieces = []
    final = {}
    with urllib.request.urlopen(request, timeout=180) as response:
        for raw in response:
            if not raw.strip():
                continue
            item = json.loads(raw)
            content = item.get("message", {}).get("content", "")
            elapsed = time.perf_counter() - started
            if content:
                pieces.append((content, elapsed))
            if item.get("done"):
                final = item
    text = "".join(x[0] for x in pieces).strip()
    return text, pieces, {
        "first_token_seconds": pieces[0][1] if pieces else None,
        "llm_total_seconds": time.perf_counter() - started,
        "done_reason": final.get("done_reason"),
        "prompt_eval_count": final.get("prompt_eval_count"),
        "eval_count": final.get("eval_count"),
    }


def replay_chunks(pieces):
    buffer = ""
    first = True
    chunks = []
    for token, ready in pieces:
        buffer += token
        while True:
            result = extract_tts_chunk(buffer, first)
            if result is None:
                break
            chunk, buffer = result
            if chunk.strip() and not is_punctuation_only(chunk):
                chunks.append({"text": chunk.strip(), "ready_seconds": ready, "is_first": first})
            first = False
    final = buffer.strip()
    if final and not is_punctuation_only(final):
        chunks.append({"text": final, "ready_seconds": pieces[-1][1] if pieces else 0.0, "is_first": first})
    return chunks


def build_tts(threads):
    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=f"{MODEL_DIR}/model.onnx",
                voices=f"{MODEL_DIR}/voices.bin",
                tokens=f"{MODEL_DIR}/tokens.txt",
                data_dir=f"{MODEL_DIR}/espeak-ng-data",
                lexicon=f"{MODEL_DIR}/lexicon-us-en.txt,{MODEL_DIR}/lexicon-zh.txt",
            ),
            provider="cpu",
            debug=False,
            num_threads=threads,
        ),
        max_num_sentences=TTS_MAX_NUM_SENTENCES,
    )
    if not cfg.validate():
        raise RuntimeError("Invalid Sherpa config")
    return sherpa_onnx.OfflineTts(cfg)


def synthesize(tts, chunks, speed):
    gc = sherpa_onnx.GenerationConfig()
    gc.sid = VOICE_ID
    gc.silence_scale = TTS_SILENCE_SCALE
    gc.speed = speed
    prior_done = 0.0
    first_audio = None
    metrics = []
    merged = []
    for chunk in chunks:
        start = time.perf_counter()
        first_cb = None
        callback_parts = []
        def callback(samples, progress):
            nonlocal first_cb
            if first_cb is None:
                first_cb = time.perf_counter() - start
            callback_parts.append(np.asarray(samples, dtype=np.float32).copy())
            return 1
        audio = tts.generate(chunk["text"], gc, callback=callback)
        elapsed = time.perf_counter() - start
        if first_cb is None:
            first_cb = elapsed
            samples = np.asarray(audio.samples, dtype=np.float32)
        else:
            samples = np.concatenate(callback_parts) if callback_parts else np.asarray(audio.samples, dtype=np.float32)
        duration = len(audio.samples) / audio.sample_rate if audio.sample_rate else 0.0
        sim_start = max(float(chunk["ready_seconds"]), prior_done)
        sim_audio = sim_start + first_cb
        prior_done = sim_start + elapsed
        if first_audio is None:
            first_audio = sim_audio
        metrics.append({
            "text": chunk["text"],
            "words": len(chunk["text"].split()),
            "ready_seconds": round(chunk["ready_seconds"], 4),
            "tts_first_audio_seconds": round(first_cb, 4),
            "tts_elapsed_seconds": round(elapsed, 4),
            "audio_duration_seconds": round(duration, 4),
            "rtf": round(elapsed / duration, 4) if duration else None,
            "simulated_audio_start_seconds": round(sim_audio, 4),
        })
        merged.append(samples)
    return {
        "simulated_first_audio_seconds": first_audio,
        "simulated_turn_done_seconds": prior_done,
        "chunks": metrics,
        "samples": np.concatenate(merged) if merged else np.array([], dtype=np.float32),
        "sample_rate": int(tts.sample_rate),
    }


def score(case, text, chunks):
    lower = text.lower()
    required = [x.lower() for x in case.get("required_any", [])]
    forbidden = [x.lower() for x in case.get("forbidden", [])]
    words = text.split()
    match = re.search(r"[.!?,;:\n]", text)
    first_clause = len((text[:match.end()] if match else text).split())
    sentence_lengths = [len(x.split()) for x in re.split(r"[.!?]+", text) if x.strip()]
    avg_sentence = statistics.mean(sentence_lengths) if sentence_lengths else len(words)
    checks = {
        "required_ok": not required or any(x in lower for x in required),
        "forbidden_ok": not any(x in lower for x in forbidden),
        "length_ok": len(words) <= int(case.get("max_words", 40)),
        "first_clause_ok": 1 <= first_clause <= 4,
        "complete": bool(re.search(r"[.!?][\"')\]]?\s*$", text)),
        "no_formatting": not bool(re.search(r"(^|\n)\s*(?:[-*#]|\d+\.)\s+", text)),
        "natural_cadence": 3 <= avg_sentence <= 16,
        "no_canned_disclaimer": not any(x in lower for x in ("as an ai", "language model", "i apologize for any confusion")),
    }
    return {
        "word_count": len(words),
        "first_clause_words": first_clause,
        "first_chunk_words": len(chunks[0]["text"].split()) if chunks else None,
        "chunk_count": len(chunks),
        "avg_sentence_words": round(avg_sentence, 3),
        "obedience_score": round(sum(checks.values()) / len(checks), 4),
        "checks": checks,
    }


def save_wav(path, samples, rate):
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def run_key(config, case_id, rep):
    return hashlib.sha256(f"{config}|{case_id}|{rep}".encode()).hexdigest()[:16]


def completed_keys(path):
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            keys.add(json.loads(line)["run_key"])
        except Exception:
            pass
    return keys


def summarize(raw, out):
    rows = []
    for line in raw.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if "error" not in item:
            rows.append(item)
    if not rows:
        return
    with (out / "runs.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["run_key","case_id","category","temperature","llm_threads","tts_speed","tts_threads","repetition","first_token_seconds","llm_total_seconds","simulated_first_audio_seconds","simulated_turn_done_seconds","obedience_score","word_count","first_clause_words","first_chunk_words","chunk_count","done_reason","response"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k) for k in fields})
    groups = {}
    for row in rows:
        key = (row["temperature"],row["llm_threads"],row["tts_speed"],row["tts_threads"])
        groups.setdefault(key, []).append(row)
    ranked = []
    for key, items in groups.items():
        fa = [x["simulated_first_audio_seconds"] for x in items if x.get("simulated_first_audio_seconds") is not None]
        ob = [x["obedience_score"] for x in items]
        td = [x["simulated_turn_done_seconds"] for x in items]
        p95 = sorted(fa)[max(0, math.ceil(len(fa)*.95)-1)] if fa else 999
        mean_fa = statistics.mean(fa) if fa else 999
        mean_ob = statistics.mean(ob)
        mean_td = statistics.mean(td)
        composite = mean_ob*100 - max(0,mean_fa-3.5)*8 - max(0,p95-5.5)*6 - max(0,mean_td-12)*.75
        ranked.append({"temperature":key[0],"llm_threads":key[1],"tts_speed":key[2],"tts_threads":key[3],"runs":len(items),"mean_obedience":round(mean_ob,4),"mean_first_audio_seconds":round(mean_fa,4),"p95_first_audio_seconds":round(p95,4),"mean_turn_done_seconds":round(mean_td,4),"composite_score":round(composite,4)})
    ranked.sort(key=lambda x:x["composite_score"], reverse=True)
    with (out / "ranked_configs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ranked[0]))
        w.writeheader(); w.writerows(ranked)
    (out / "top_10.json").write_text(json.dumps(ranked[:10], indent=2), encoding="utf-8")


def main():
    args = parse_args()
    configs, default_reps = grid(args.mode)
    reps = args.repetitions or default_reps
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw_results.jsonl"
    completed = completed_keys(raw) if args.resume else set()
    system_prompt = Path(SYSTEM_PROMPT_FILE).read_text(encoding="utf-8").strip()
    print(f"mode={args.mode} configs={len(configs)} cases={len(cases)} reps={reps} total={len(configs)*len(cases)*reps}")
    tts_cache = {}
    counter = 0
    for config in configs:
        if config.tts_threads not in tts_cache:
            print(f"Loading TTS threads={config.tts_threads}")
            tts_cache[config.tts_threads] = build_tts(config.tts_threads)
        tts = tts_cache[config.tts_threads]
        for case in cases:
            for rep in range(1, reps+1):
                key = run_key(config, case["id"], rep)
                if key in completed:
                    continue
                counter += 1
                print(f"[{counter}] {case['id']} rep={rep} temp={config.temperature} lt={config.llm_threads} speed={config.tts_speed} tt={config.tts_threads}", flush=True)
                try:
                    response, pieces, llm = stream_ollama(args.model, messages_for(system_prompt, case), config.temperature, config.llm_threads)
                    chunks = replay_chunks(pieces)
                    tts_data = synthesize(tts, chunks, config.tts_speed)
                    row = {
                        "run_key": key, "case_id": case["id"], "category": case["category"],
                        "temperature": config.temperature, "llm_threads": config.llm_threads,
                        "tts_speed": config.tts_speed, "tts_threads": config.tts_threads,
                        "repetition": rep, "response": response, **llm,
                        "simulated_first_audio_seconds": round(tts_data["simulated_first_audio_seconds"],4) if tts_data["simulated_first_audio_seconds"] is not None else None,
                        "simulated_turn_done_seconds": round(tts_data["simulated_turn_done_seconds"],4),
                        "chunk_metrics": tts_data["chunks"], **score(case,response,chunks),
                    }
                    with raw.open("a", encoding="utf-8") as f: f.write(json.dumps(row, ensure_ascii=False)+"\n")
                    if args.save_wavs and rep == 1 and case["category"] in {"question","memory","presence"}:
                        name = f"{case['id']}__t{config.temperature}__lt{config.llm_threads}__s{config.tts_speed}__tt{config.tts_threads}.wav"
                        save_wav(out/"wav_samples"/name, tts_data["samples"], tts_data["sample_rate"])
                    print(f"first_token={row['first_token_seconds']:.3f}s first_audio={row['simulated_first_audio_seconds']:.3f}s obedience={row['obedience_score']:.3f} response={response!r}")
                except Exception as e:
                    with raw.open("a", encoding="utf-8") as f: f.write(json.dumps({"run_key":key,"case_id":case["id"],"temperature":config.temperature,"llm_threads":config.llm_threads,"tts_speed":config.tts_speed,"tts_threads":config.tts_threads,"repetition":rep,"error":repr(e)})+"\n")
                    print(f"ERROR {e!r}")
                summarize(raw,out)
    summarize(raw,out)
    print(f"Complete. See {out/'ranked_configs.csv'}")


if __name__ == "__main__":
    main()
