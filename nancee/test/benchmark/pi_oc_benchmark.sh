#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-phi4-mini:3.8b}"
RUNS="${2:-10}"
PROMPT="${3:-Hello Nancee, give me a short one sentence status check.}"

OUT_DIR="$HOME/Nancee/nancee/test/benchmark/results"
mkdir -p "$OUT_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$OUT_DIR/benchmark_${MODEL//[:\/]/_}_${STAMP}.csv"

echo "model,run,arm_clock_hz,temp_c,throttled,total_s,eval_count,eval_duration_s,tokens_per_s,response" > "$OUT"

echo "[INFO] Model: $MODEL"
echo "[INFO] Runs: $RUNS"
echo "[INFO] Output: $OUT"
echo

echo "[INFO] Current Pi state:"
vcgencmd measure_clock arm || true
vcgencmd measure_temp || true
vcgencmd get_throttled || true
echo

echo "[INFO] Warming model..."
curl -s http://127.0.0.1:11434/api/generate \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"warmup\",\"stream\":false}" >/dev/null

for i in $(seq 1 "$RUNS"); do
  echo "[RUN $i/$RUNS]"

  ARM_CLOCK="$(vcgencmd measure_clock arm 2>/dev/null | awk -F= '{print $2}' || echo unknown)"
  TEMP="$(vcgencmd measure_temp 2>/dev/null | sed -E "s/temp=([0-9.]+)'C/\1/" || echo unknown)"
  THROTTLED="$(vcgencmd get_throttled 2>/dev/null | awk -F= '{print $2}' || echo unknown)"

  START_NS="$(date +%s%N)"

  JSON_PAYLOAD="$(jq -nc \
  --arg model "$MODEL" \
  --arg prompt "$PROMPT" \
  --arg temp "${LLM_TEMPERATURE:-0}" \
  --arg predict "${LLM_NUM_PREDICT:-48}" \
  --arg threads "${LLM_NUM_THREADS:-4}" \
  '{model:$model,prompt:$prompt,stream:false,options:{
    temperature:($temp|tonumber),
    num_predict:($predict|tonumber),
    num_thread:($threads|tonumber)
  }}')"

JSON="$(curl -s http://127.0.0.1:11434/api/generate -d "$JSON_PAYLOAD")"

  END_NS="$(date +%s%N)"
  TOTAL_S="$(awk "BEGIN {print ($END_NS - $START_NS) / 1000000000}")"

  RESPONSE="$(echo "$JSON" | jq -r '.response // ""' | tr '\n' ' ' | sed 's/"/""/g')"
  EVAL_COUNT="$(echo "$JSON" | jq -r '.eval_count // 0')"
  EVAL_DURATION_NS="$(echo "$JSON" | jq -r '.eval_duration // 0')"

  EVAL_DURATION_S="$(awk "BEGIN {print $EVAL_DURATION_NS / 1000000000}")"

  if [ "$EVAL_DURATION_NS" != "0" ] && [ "$EVAL_COUNT" != "0" ]; then
    TOKENS_PER_S="$(awk "BEGIN {print $EVAL_COUNT / ($EVAL_DURATION_NS / 1000000000)}")"
  else
    TOKENS_PER_S="0"
  fi

  echo "$MODEL,$i,$ARM_CLOCK,$TEMP,$THROTTLED,$TOTAL_S,$EVAL_COUNT,$EVAL_DURATION_S,$TOKENS_PER_S,\"$RESPONSE\"" >> "$OUT"

  echo "  clock=$ARM_CLOCK temp=$TEMP throttled=$THROTTLED total=${TOTAL_S}s tok/s=$TOKENS_PER_S"
done

echo
echo "[SUMMARY]"
column -s, -t "$OUT" | tail -n +"1"

echo
echo "[DONE] Results saved to:"
echo "$OUT"
