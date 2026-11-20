#!/usr/bin/env bash

# Include first-run preparation and the serial console; Ctrl+C leaves QEMU running.
set -euo pipefail
cd "$(dirname "$0")"
exec docker logs --follow "$@" "$(python3 -m project.defaults container)"
