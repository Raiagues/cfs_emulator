#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
    simulate) shift; exec ./start --no-ui simulate "$@" ;;
    values) shift; exec ./start --no-ui values --target qemu "$@" ;;
    *) exec ./start --no-ui project "$@" ;;
esac
