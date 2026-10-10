#!/usr/bin/env bash
# Fast pre-push check; see scripts/gate/quick_gate.py.
set -euo pipefail
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python
exec "$PY" "$(dirname "$0")/quick_gate.py" "$@"
