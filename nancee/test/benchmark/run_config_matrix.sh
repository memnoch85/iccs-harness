#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-phi4-mini:3.8b}"
RUNS="${2:-20}"

cd /home/memnoch/Nancee/nancee/test/benchmark

run_case() {
  local name="$1"
  shift

  echo
  echo "============================================================"
  echo "CONFIG: $name"
  echo "MODEL:  $MODEL"
  echo "RUNS:   $RUNS"
  echo "============================================================"

  env "$@" ./pi_oc_benchmark.sh "$MODEL" "$RUNS"
}

run_case "llm_threads_4_baseline" \
  LLM_NUM_THREADS=4 \
  LLM_TEMPERATURE=0 \
  LLM_NUM_PREDICT=48

run_case "llm_threads_3_candidate" \
  LLM_NUM_THREADS=3 \
  LLM_TEMPERATURE=0 \
  LLM_NUM_PREDICT=48
