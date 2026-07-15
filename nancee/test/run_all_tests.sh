#!/usr/bin/env bash

set -uo pipefail

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd
)"

REPO_ROOT="$(
    cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1
    pwd
)"

COMM_TEST_TIMEOUT_SECONDS="${COMM_TEST_TIMEOUT_SECONDS:-120}"
DATABASE_TEST_TIMEOUT_SECONDS="${DATABASE_TEST_TIMEOUT_SECONDS:-30}"

if [[ "$EUID" -ne 0 ]]; then
    echo "Run with sudo:"
    echo "  sudo $0"
    exit 1
fi

cd "$REPO_ROOT" || {
    echo "FAIL: Could not enter repository root: $REPO_ROOT"
    exit 1
}

if [[ -n "${PYTHON_BIN:-}" ]]; then
    python_bin="$PYTHON_BIN"
elif [[ -x "${REPO_ROOT}/venv/bin/python" ]]; then
    python_bin="${REPO_ROOT}/venv/bin/python"
else
    python_bin="$(command -v python3 || true)"
fi

if [[ -z "$python_bin" || ! -x "$python_bin" ]]; then
    echo "FAIL: Could not locate a usable Python interpreter."
    exit 1
fi

if ! command -v timeout >/dev/null 2>&1; then
    echo "FAIL: The timeout command is not installed."
    exit 1
fi

export PYTHONPATH="${REPO_ROOT}/sherpa${PYTHONPATH:+:${PYTHONPATH}}"

passed=0
failed=0
failed_tests=()

run_test() {
    local test_name="$1"
    shift

    echo
    echo "============================================================"
    echo "RUNNING: $test_name"
    echo "============================================================"

    "$@"
    local exit_code=$?

    if [[ "$exit_code" -eq 0 ]]; then
        echo "[PASS] $test_name"
        passed=$((passed + 1))
    else
        echo "[FAIL] $test_name exited with code $exit_code"
        failed=$((failed + 1))
        failed_tests+=("$test_name (exit $exit_code)")
    fi
}

mapfile -t python_files < <(
    find \
        "${REPO_ROOT}/sherpa" \
        "${REPO_ROOT}/test/unit" \
        -path '*/venv/*' -prune -o \
        -path '*/__pycache__/*' -prune -o \
        -type f -name '*.py' -print |
        sort
)

shell_test_files=(
    "${SCRIPT_DIR}/testDatabaseReadWrite.sh"
    "${SCRIPT_DIR}/testComms.sh"
)

database_test="${SCRIPT_DIR}/testDatabaseReadWrite.sh"
communication_test="${SCRIPT_DIR}/testComms.sh"

echo "NANCEE test runner"
echo "Repository: $REPO_ROOT"
echo "Python: $python_bin"
echo "Database timeout: ${DATABASE_TEST_TIMEOUT_SECONDS}s"
echo "Communication timeout: ${COMM_TEST_TIMEOUT_SECONDS}s"

run_test \
    "Python compile check" \
    "$python_bin" \
    -B \
    -m py_compile \
    "${python_files[@]}"

run_test \
    "Python unit tests" \
    "$python_bin" \
    -B \
    -m unittest discover \
    -s "${REPO_ROOT}/test/unit" \
    -p 'test_*.py' \
    -v

run_test \
    "Shell test syntax checks" \
    bash \
    -n \
    "${shell_test_files[@]}"

run_test \
    "SQLite database read/write test" \
    timeout \
    "${DATABASE_TEST_TIMEOUT_SECONDS}s" \
    bash \
    "$database_test"

run_test \
    "Full CAN communication test" \
    timeout \
    "${COMM_TEST_TIMEOUT_SECONDS}s" \
    bash \
    "$communication_test"

echo
echo "============================================================"
echo "TEST SUMMARY"
echo "============================================================"
echo "Passed: $passed"
echo "Failed: $failed"

if ((failed > 0)); then
    echo
    echo "Failed tests:"

    for failed_test in "${failed_tests[@]}"; do
        echo "  - $failed_test"
    done

    echo
    echo "NANCEE is not clean and green."
    exit 1
fi

echo
echo "NANCEE is clean and green."
exit 0
