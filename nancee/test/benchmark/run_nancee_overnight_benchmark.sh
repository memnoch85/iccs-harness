#!/usr/bin/env bash
set -uo pipefail

REPO_ROOT="${HOME}/Nancee/nancee"
BENCH_DIR="${REPO_ROOT}/test/benchmark"
RESULT_DIR="${BENCH_DIR}/results-6h"

cd "${REPO_ROOT}"
source sherpa/venv/bin/activate

export NANCEE_MEMORY_DEBUG=false
export SPEED=1.2

mkdir -p "${RESULT_DIR}"

echo "[BENCHMARK] Starting focused six-hour run."
echo "[BENCHMARK] Results: ${RESULT_DIR}"
echo "[BENCHMARK] Started: $(date --iso-8601=seconds)"

# SIGINT gives Python a chance to stop cleanly.
# Results are summarized after every completed run, so even a
# timeout leaves usable ranked CSV and JSON files.
timeout \
  --signal=INT \
  --kill-after=5m \
  6h \
  python3 "${BENCH_DIR}/nancee_overnight_benchmark.py" \
    --mode overnight \
    --resume \
    --save-wavs \
    --cases "${BENCH_DIR}/benchmark_cases.json" \
    --output "${RESULT_DIR}" \
  2>&1 | tee -a "${RESULT_DIR}/benchmark.log"

status=${PIPESTATUS[0]}

echo "[BENCHMARK] Ended: $(date --iso-8601=seconds)"
echo "[BENCHMARK] Exit status: ${status}"

# timeout normally returns 124 after reaching the six-hour cap.
if [[ "${status}" -eq 0 || "${status}" -eq 124 || "${status}" -eq 130 ]]; then
    exit 0
fi

exit "${status}"
