#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$SCRIPT_DIR/benchmark_logs"

mkdir -p "$LOG_DIR"

run_profile() {
    local profile="$1"

    case "$profile" in
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
            echo "Unknown profile: $profile"
            exit 1
            ;;
    esac

    export NANCEE_RESPONSE_ACK_TEMPERATURE=0.25
    export NANCEE_RESPONSE_ACK_NUM_PREDICT=18
    export NANCEE_MEMORY_DEBUG=true

    # Disable the initial bridge while comparing answer quality.
    export NANCEE_LATENCY_BRIDGE_ENABLED=false

    local stamp
    stamp="$(date +%Y%m%d-%H%M%S)"

    local log
    log="$LOG_DIR/${stamp}-profile-${profile}.log"

    echo
    echo "============================================================"
    echo "PROFILE $profile"
    echo "Log: $log"
    echo
    echo "Speak these prompts in order:"
    echo
    echo " 1. Hey Nancee, I bought a green duffel bag at Target today."
    echo " 2. I finished soldering a CAN transceiver yesterday."
    echo " 3. What is my name?"
    echo " 4. What did I buy at Target?"
    echo " 5. What did I finish soldering?"
    echo " 6. What is my sister's middle name?"
    echo " 7. Actually, the duffel bag was blue, not green."
    echo " 8. What color was the duffel bag?"
    echo " 9. Did you buy the duffel bag, or did I?"
    echo "10. What is the capital of France?"
    echo "11. Explain in two sentences how a turbocharger works."
    echo "12. Give me a brief history of Sauron and state his relationship to Morgoth."
    echo "13. Morgoth was Sauron's master, right?"
    echo "14. Hardly drive."
    echo
    echo "Press Ctrl+C after prompt 14."
    echo "============================================================"
    echo

    cd "$PROJECT_ROOT"
    source sherpa/venv/bin/activate

    set +e
    python3 sherpa/nancee_chat.py 2>&1 | tee "$log"
    local status="${PIPESTATUS[0]}"
    set -e

    echo
    echo "Profile $profile finished with status $status"
    echo "Saved: $log"
}

for profile in A B C
do
    run_profile "$profile"

    echo
    read -r -p "Press Enter to start the next profile..."
done

echo
echo "============================================================"
echo "ALL QUALITY PROFILES COMPLETE"
echo "Logs are in:"
echo "$LOG_DIR"
echo "============================================================"
