#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Run the selected project profile through the shared execution controls.
if (($#)); then
    echo "Usage: ./run.sh" >&2
    exit 2
fi
# Reuse Studio's process checks and execution.lock; never restart an active cFS.
exec ./start --no-ui run
