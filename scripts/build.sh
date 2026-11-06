#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

# Use the same image name for local builds and published releases.
docker build -t "$(python3 -m hardware.infrastructure image)" "$@" .
