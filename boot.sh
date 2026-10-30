#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Mount only the public key; the private key stays on the PC.
SSH_KEY="$(realpath "${1:-$HOME/.ssh/id_ed25519.pub}")"
test -f "$SSH_KEY"
mkdir -p logs
LOG_FILE="$(mktemp "logs/boot-$(date +%Y%m%d-%H%M%S)-XXXXXX.log")"
ln -sfn "${LOG_FILE##*/}" logs/latest.log

# Keep the Linux console interactive and expose SSH only on localhost.
exec docker run --rm -it --name pi4-cfs \
    --user "$(id -u):$(id -g)" \
    -p 127.0.0.1:2222:2222 \
    -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro \
    -v "$PWD:/work" -v "$SSH_KEY:/ssh.pub:ro" \
    pi4-emulator:dev "/work/$LOG_FILE"
