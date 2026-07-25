#!/usr/bin/env bash
set -euo pipefail

repo="${1:-$HOME/Nancee/nancee}"
order="${2:-tpc-first}"
interturn_seconds="${NANCEE_BENCH_INTERTURN_SECONDS:-4.5}"
num_predict="${NANCEE_BENCH_NUM_PREDICT:-12}"
cooldown_seconds="${NANCEE_BENCH_COOLDOWN_SECONDS:-15}"

cd "$repo"

model="$({ PYTHONPATH=sherpa python3 - <<'PY'
from config import LLM_MODEL
print(LLM_MODEL)
PY
} 2>/dev/null)"

stamp="$(date +%Y%m%d-%H%M%S)"
result_dir="$HOME/nancee-tpc-benchmark-$stamp-$order"
mkdir -p "$result_dir"

case "$order" in
    tpc-first)
        modes=(tpc no-tpc)
        ;;
    no-tpc-first)
        modes=(no-tpc tpc)
        ;;
    *)
        echo "Order must be tpc-first or no-tpc-first." >&2
        exit 2
        ;;
esac

{
    echo "repo=$repo"
    echo "model=$model"
    echo "order=$order"
    echo "interturn_seconds=$interturn_seconds"
    echo "num_predict=$num_predict"
    echo "cooldown_seconds=$cooldown_seconds"
    command -v vcgencmd >/dev/null 2>&1 && vcgencmd measure_temp || true
    command -v vcgencmd >/dev/null 2>&1 && vcgencmd get_throttled || true
} | tee "$result_dir/environment.txt"

for mode in "${modes[@]}"; do
    echo
    echo "=== Running $mode ==="
    ollama stop "$model" >/dev/null 2>&1 || true
    sleep "$cooldown_seconds"

    NANCEE_MEMORY_DEBUG=false PYTHONPATH=sherpa python3 tools/tpc_routing_benchmark.py \
        --mode "$mode" \
        --interturn-seconds "$interturn_seconds" \
        --num-predict "$num_predict" \
        --output "$result_dir/$mode.csv" \
        2>&1 | tee "$result_dir/$mode.log"

done

python3 tools/compare_tpc_routing_benchmark.py \
    --tpc "$result_dir/tpc.summary.json" \
    --no-tpc "$result_dir/no-tpc.summary.json" \
    --output "$result_dir/comparison.md" \
    | tee "$result_dir/comparison.txt"

{
    command -v vcgencmd >/dev/null 2>&1 && vcgencmd measure_temp || true
    command -v vcgencmd >/dev/null 2>&1 && vcgencmd get_throttled || true
} | tee "$result_dir/environment.after.txt"

echo
echo "Benchmark complete: $result_dir"
echo "Read: $result_dir/comparison.md"
