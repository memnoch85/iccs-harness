#!/bin/bash

# -----------------------------
# CONFIG
# -----------------------------
BASE_DIR="/home/memnoch/Nancee/nancee/test"
FLAT_FILE="$BASE_DIR/flatFileCommsTest.log"
RESULT_LOG="$BASE_DIR/commsResult.log"

WRITER_SCRIPT="$BASE_DIR/testpico2PiWriteComms.sh"
SQL_SCRIPT="$BASE_DIR/testflatFile2SQL.sh"

WRITER_PID=""

# -----------------------------
# CLEANUP FUNCTION (CRITICAL)
# -----------------------------
cleanup() {
  echo "=== CLEANUP ==="

  if [[ -n "$WRITER_PID" ]]; then
    echo "Killing writer PID: $WRITER_PID"
    kill "$WRITER_PID" 2>/dev/null || true
    wait "$WRITER_PID" 2>/dev/null || true
  fi

  # Kill anything still holding serial (paranoid but safe)
  fuser -k /dev/serial0 2>/dev/null || true

  echo "Cleanup complete"
}

# Trap ALL exits (normal + Ctrl+C)
trap cleanup EXIT INT TERM

# -----------------------------
# PRE-CLEANUP
# -----------------------------
echo "=== PRE-CLEANUP ==="
rm -f "$FLAT_FILE"
rm -f "$RESULT_LOG"

# -----------------------------
# START WRITER (BACKGROUND)
# -----------------------------
echo "Starting UART writer..."
bash "$WRITER_SCRIPT" >> "$RESULT_LOG" 2>&1 &
WRITER_PID=$!

echo "Writer PID: $WRITER_PID"

# -----------------------------
# WAIT FOR DATA (NOT JUST FILE)
# -----------------------------
echo "Waiting for flat file data..."
TIMEOUT=10
COUNT=0

while [[ $COUNT -lt $TIMEOUT ]]; do
  if [[ -s "$FLAT_FILE" ]]; then
    break
  fi
  sleep 1
  ((COUNT++))
done

if [[ ! -s "$FLAT_FILE" ]]; then
  echo "Flat file empty or not created" | tee -a "$RESULT_LOG"
  exit 1
fi

# Give it a moment to stabilize
sleep 2

echo "Flat file contents:"
cat "$FLAT_FILE"

# -----------------------------
# RUN SQL INGEST
# -----------------------------
echo "Running SQL ingest..."
bash "$SQL_SCRIPT" >> "$RESULT_LOG" 2>&1
rm -f "$FLAT_FILE"
# -----------------------------
# DONE 
# -----------------------------
echo "=== RUN COMPLETE ==="
cat "$RESULT_LOG"
