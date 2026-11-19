#!/usr/bin/env bash
# Provision the host tools used for the native target and the NASA Ground System.
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/}python3" -m hardware.host_tools "$@"
