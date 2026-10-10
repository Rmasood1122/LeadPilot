#!/usr/bin/env bash
# Merge policy B (docs/program/DECISIONS.md MERGE-B): the only sanctioned way
# to merge into master. All logic lives in safe_merge.py; see its docstring.
set -euo pipefail
exec python3 "$(dirname "$0")/safe_merge.py" "$@"
