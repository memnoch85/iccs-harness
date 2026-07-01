#!/usr/bin/env bash

set -euo pipefail

DB_PATH="${NANCEE_DB_PATH:-/nancee/db/nancee.db}"
TEST_TOKEN="NANCEE_DB_TEST_$(date +%s)_$$"

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "FAIL: sqlite3 is not installed or not available in PATH."
    exit 1
fi

if [[ ! -f "$DB_PATH" ]]; then
    echo "FAIL: Database does not exist: $DB_PATH"
    exit 1
fi

echo "=== NANCEE Database Read/Write Test ==="
echo "Database: $DB_PATH"

result="$(
    sqlite3 -batch "$DB_PATH" <<SQL
.bail on
.headers off
.mode list

PRAGMA busy_timeout = 5000;

BEGIN IMMEDIATE;

INSERT INTO user_profile (
    name,
    preferred_name,
    tone,
    verbosity,
    preferences_json
)
VALUES (
    '$TEST_TOKEN',
    'Database Test',
    'neutral',
    'short',
    '{"temporary_test":true}'
);

SELECT
    'user_profile|' || COUNT(*)
FROM user_profile
WHERE name = '$TEST_TOKEN';


INSERT INTO vehicle_state (
    pid,
    value
)
VALUES (
    '$TEST_TOKEN',
    123.45
);

SELECT
    'vehicle_state|' || COUNT(*)
FROM vehicle_state
WHERE pid = '$TEST_TOKEN'
  AND value = 123.45;


INSERT INTO vehicle_issues (
    issue_code,
    severity,
    description,
    recommendation,
    resolved
)
VALUES (
    '$TEST_TOKEN',
    'test',
    'Temporary database test issue',
    'No action required',
    0
);

SELECT
    'vehicle_issues|' || COUNT(*)
FROM vehicle_issues
WHERE issue_code = '$TEST_TOKEN'
  AND resolved = 0;


ROLLBACK;


SELECT
    'cleanup_user_profile|' || COUNT(*)
FROM user_profile
WHERE name = '$TEST_TOKEN';

SELECT
    'cleanup_vehicle_state|' || COUNT(*)
FROM vehicle_state
WHERE pid = '$TEST_TOKEN';

SELECT
    'cleanup_vehicle_issues|' || COUNT(*)
FROM vehicle_issues
WHERE issue_code = '$TEST_TOKEN';
SQL
)"

echo "$result"

expected_results=(
    "user_profile|1"
    "vehicle_state|1"
    "vehicle_issues|1"
    "cleanup_user_profile|0"
    "cleanup_vehicle_state|0"
    "cleanup_vehicle_issues|0"
)

for expected in "${expected_results[@]}"; do
    if ! grep -Fxq "$expected" <<<"$result"; then
        echo "FAIL: Expected result was not found:"
        echo "  $expected"
        exit 1
    fi
done

echo "PASS: user_profile read/write succeeded."
echo "PASS: vehicle_state read/write succeeded."
echo "PASS: vehicle_issues read/write succeeded."
echo "PASS: Temporary rows were rolled back."
