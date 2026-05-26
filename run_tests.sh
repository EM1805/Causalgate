#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
if [[ "${CAUSALGATE_STDLIB_TESTS:-0}" == "1" ]]; then
  python -S tools/run_tests.py "$@"
else
  python tools/run_tests.py "$@"
fi
