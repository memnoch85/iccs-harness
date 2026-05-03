#!/bin/bash

DB_PATH="/nancee/db/nancee.db"
INPUT_FILE="flatFileCommsTest.log"

echo "=== Nancee DB Write Test ==="

# 1. Read latest line from file
if [[ ! -f "$INPUT_FILE" ]]; then
  echo "Input file not found: $INPUT_FILE"
  exit 1
fi

LINE=$(tail -n 1 "$INPUT_FILE")

if [[ -z "$LINE" ]]; then
  echo "No data found in input file"
  exit 1
fi

echo "Read line: $LINE"

# 2. Tag it as test data
TEST_DATA="INIT_TEST|$LINE"

# 3. Insert into DB
sqlite3 "$DB_PATH" <<EOF
INSERT INTO raw_log (raw) VALUES ('$TEST_DATA');
EOF

if [[ $? -ne 0 ]]; then
  echo "-----Insert failed"
  exit 1
fi

echo "Inserted: $TEST_DATA"

# 4. Validate write (fetch latest entry)
RESULT=$(sqlite3 "$DB_PATH" "
SELECT raw FROM raw_log 
ORDER BY id DESC 
LIMIT 1;
")

echo "DB returned: $RESULT"

# 5. Verify match
if [[ "$RESULT" == "$TEST_DATA" ]]; then
  echo "-----SUCCESS: Write verified"
else
  echo "----FAILURE: Mismatch"
  exit 1
fi
