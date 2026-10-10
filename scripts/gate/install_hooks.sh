#!/usr/bin/env bash
# Point git at the repo's committed hooks (.githooks/). Run once per clone.
set -euo pipefail
root=$(git rev-parse --show-toplevel)
git -C "$root" config core.hooksPath .githooks
chmod +x "$root/.githooks/"* 2>/dev/null || true
echo "Installed: core.hooksPath=.githooks (pre-push runs scripts/gate/quick_gate.py)."
