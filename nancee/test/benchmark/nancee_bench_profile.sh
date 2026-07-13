#!/usr/bin/env bash
set -euo pipefail

QUALITY_PROFILE="${1:-}"
BRIDGE_PROFILE="${2:-}"

if [[ -z "$QUALITY_PROFILE" || -z "$BRIDGE_PROFILE" ]]; then
    echo "Usage: $0 <A|B|C> <off|1|2|3>"
    exit 2
fi

case "$QUALITY_PROFILE" in
    A)
        export NANCEE_RESPONSE_NORMAL_TEMPERATURE=0.30
        export NANCEE_RESPONSE_NORMAL_NUM_PREDICT=36
        export NANCEE_RESPONSE_DETAILED_TEMPERATURE=0.30
        export NANCEE_RESPONSE_DETAILED_NUM_PREDICT=65
        export NANCEE_RESPONSE_RECALL_TEMPERATURE=0.15
        export NANCEE_RESPONSE_RECALL_NUM_PREDICT=18
        ;;
    B)
        export NANCEE_RESPONSE_NORMAL_TEMPERATURE=0.20
        export NANCEE_RESPONSE_NORMAL_NUM_PREDICT=48
        export NANCEE_RESPONSE_DETAILED_TEMPERATURE=0.20
        export NANCEE_RESPONSE_DETAILED_NUM_PREDICT=80
        export NANCEE_RESPONSE_RECALL_TEMPERATURE=0.10
        export NANCEE_RESPONSE_RECALL_NUM_PREDICT=18
        ;;
    C)
        export NANCEE_RESPONSE_NORMAL_TEMPERATURE=0.25
        export NANCEE_RESPONSE_NORMAL_NUM_PREDICT=44
        export NANCEE_RESPONSE_DETAILED_TEMPERATURE=0.25
        export NANCEE_RESPONSE_DETAILED_NUM_PREDICT=72
        export NANCEE_RESPONSE_RECALL_TEMPERATURE=0.12
        export NANCEE_RESPONSE_RECALL_NUM_PREDICT=18
        ;;
    *)
        echo "Unknown quality profile: $QUALITY_PROFILE"
        exit 2
        ;;
esac

# User requested that acknowledgement behavior remain unchanged.
export NANCEE_RESPONSE_ACK_TEMPERATURE=0.25
export NANCEE_RESPONSE_ACK_NUM_PREDICT=18
export NANCEE_MEMORY_DEBUG=true

case "$BRIDGE_PROFILE" in
    off)
        export NANCEE_LATENCY_BRIDGE_ENABLED=false
        BRIDGE_LABEL="bridge-off"
        ;;
    1)
        export NANCEE_LATENCY_BRIDGE_ENABLED=true
        export NANCEE_LATENCY_BRIDGE_NORMAL_SECONDS=6.3
        export NANCEE_LATENCY_BRIDGE_RECALL_SECONDS=5.2
        BRIDGE_LABEL="bridge-6.3-5.2"
        ;;
    2)
        export NANCEE_LATENCY_BRIDGE_ENABLED=true
        export NANCEE_LATENCY_BRIDGE_NORMAL_SECONDS=6.8
        export NANCEE_LATENCY_BRIDGE_RECALL_SECONDS=5.8
        BRIDGE_LABEL="bridge-6.8-5.8"
        ;;
    3)
        export NANCEE_LATENCY_BRIDGE_ENABLED=true
        export NANCEE_LATENCY_BRIDGE_NORMAL_SECONDS=7.3
        export NANCEE_LATENCY_BRIDGE_RECALL_SECONDS=6.3
        BRIDGE_LABEL="bridge-7.3-6.3"
        ;;
    *)
        echo "Unknown bridge profile: $BRIDGE_PROFILE"
        exit 2
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$SCRIPT_DIR/benchmark_logs"

cd "$ROOT"

mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/${STAMP}-quality-${QUALITY_PROFILE}-${BRIDGE_LABEL}.log"

echo "============================================================"
echo "NANCEE BENCHMARK"
echo "quality_profile=$QUALITY_PROFILE"
echo "bridge_profile=$BRIDGE_PROFILE"
echo "log=$LOG"
echo "normal_temp=$NANCEE_RESPONSE_NORMAL_TEMPERATURE"
echo "normal_tokens=$NANCEE_RESPONSE_NORMAL_NUM_PREDICT"
echo "detailed_temp=$NANCEE_RESPONSE_DETAILED_TEMPERATURE"
echo "detailed_tokens=$NANCEE_RESPONSE_DETAILED_NUM_PREDICT"
echo "recall_temp=$NANCEE_RESPONSE_RECALL_TEMPERATURE"
echo "recall_tokens=$NANCEE_RESPONSE_RECALL_NUM_PREDICT"
echo "bridge_enabled=$NANCEE_LATENCY_BRIDGE_ENABLED"
echo "============================================================"

source sherpa/venv/bin/activate

python3 sherpa/nancee_chat.py 2>&1 | tee "$LOG"
