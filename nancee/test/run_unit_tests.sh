#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$ROOT/nancee/sherpa/venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3)"
fi

export PYTHONPATH="$ROOT/nancee:$ROOT/nancee/sherpa${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON" -B -m unittest discover \
    -s "$ROOT/nancee/test/unit" \
    -p 'test_*.py' "$@"
