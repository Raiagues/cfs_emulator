#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

# Use the same image name for local builds and published releases.
docker build --build-arg "REGISTER_MODELS=$(python3 project/qemu/generate.py --fingerprint)" -t "$(python3 -m hardware.infrastructure image)" "$@" .
