#!/usr/bin/env bash
# Full gate: run locally what CI's required checks run, before marking a PR
# ready. Use it in a Claude Code cloud session (no compute charge) instead of
# spending GitHub Actions minutes on trial and error.
#
#   1. the offline release gate (the four commands in CLAUDE.md)
#   2. the PostgreSQL integration suite, if PostgreSQL is reachable at
#      $TEST_DATABASE_URL (the URL tests/integration/conftest.py uses; its
#      default is postgresql://leadpilot:leadpilot@localhost:5433/clienthunter_test)
#   3. the frontend checks, if frontend/node_modules exists
#
# Every step's exit code is read directly (never through a pipe). Exit 0 only
# if every step that ran passed; a skipped step is reported as SKIPPED, never
# as passed.
set -uo pipefail
root=$(git rev-parse --show-toplevel)
cd "$root"
PY="${PYTHON:-python3}"
declare -a summary=()
failed=0

run_step() {
  local name="$1"; shift
  local start=$SECONDS
  "$@"
  local code=$?
  summary+=("$(printf '%-28s exit %-3s %4ss' "$name" "$code" "$((SECONDS - start))")")
  [ "$code" -eq 0 ] || failed=1
}

run_step "registry lint"       "$PY" evals/tools/registry_lint.py evals/registry.yaml
run_step "offline suite"       "$PY" evals/run_evals.py
run_step "promote gate"        "$PY" evals/tools/promote.py
run_step "block fixtures"      "$PY" evals/fixtures/verify_block_fixtures.py

PG_URL="${TEST_DATABASE_URL:-postgresql://leadpilot:leadpilot@localhost:5433/clienthunter_test}"
if "$PY" -c "import sys,sqlalchemy as s; s.create_engine(sys.argv[1]).connect().close()" "$PG_URL" 2>/dev/null; then
  run_step "postgres integration" "$PY" -m pytest tests/integration -q -p no:cacheprovider
else
  summary+=("$(printf '%-28s SKIPPED (no PostgreSQL at TEST_DATABASE_URL)' 'postgres integration')")
fi

if [ -d frontend/node_modules ]; then
  run_step "frontend type-check" npm --prefix frontend run --silent type-check
  run_step "frontend lint"       npm --prefix frontend run --silent lint
  run_step "frontend unit tests" npm --prefix frontend run --silent test
else
  summary+=("$(printf '%-28s SKIPPED (run npm ci in frontend/)' 'frontend')")
fi

echo
echo "full_gate summary:"
printf '  %s\n' "${summary[@]}"
if [ "$failed" -ne 0 ]; then echo "full_gate: FAILED"; exit 1; fi
echo "full_gate: every step that ran passed."
