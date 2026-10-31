#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Keep the CLI shared by the terminal and a future GUI.
case "${1:-}" in
    devices)
        exec docker run --rm --entrypoint python3 \
            -v "$PWD/project:/work/project:ro" -v "$PWD/sensors:/work/sensors:ro" \
            "$(cat config/image)" /work/sensors/runtime.py devices ;;
    simulate)
        shift
        exec python3 sensors/simulator.py "$@" ;;
    values)
        exec python3 sensors/runtime.py values ;;
    *) exec python3 project/manage.py "$@" ;;
esac
