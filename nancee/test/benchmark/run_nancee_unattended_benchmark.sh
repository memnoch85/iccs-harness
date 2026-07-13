#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

source sherpa/venv/bin/activate

# Keep output readable. The benchmark records its own retrieval and score data.
export NANCEE_MEMORY_DEBUG=false

MINUTES="${1:-110}"

exec python3 \
  test/benchmark/bench_nancee_unattended.py \
  --minutes "$MINUTES"
