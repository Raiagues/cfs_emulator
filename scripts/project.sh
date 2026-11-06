#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Project commands for the terminal and the Studio backend (Workspace.mutate, values).
case "${1:-}" in
    devices)
        exec docker run --rm --entrypoint python3 \
            -v "$PWD/project:/work/project:ro" -v "$PWD/sensors:/work/sensors:ro" \
            "$(python3 -m hardware.infrastructure image)" /work/sensors/runtime.py devices ;;
    simulate)
        shift
        exec python3 sensors/simulator.py "$@" ;;
    values)
        exec python3 sensors/runtime.py values ;;
    *) exec python3 project/manage.py "$@" ;;
esac
