#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Run in the background unless the serial console is requested.
MODE=(-d)
case "${1:-}" in
    "") ;;
    --interactive) MODE=(-it) ;;
    *) echo "Usage: ./boot.sh [--interactive]" >&2; exit 2 ;;
esac

# Each checkout has its own local key; personal SSH keys are never used.
if [[ ! -f .ssh/id_ed25519 ]]; then
    if [[ -e board/raspios.qcow2 ]]; then
        echo "Restore this disk's .ssh/ directory before booting." >&2
        exit 1
    fi
    mkdir -p .ssh
    chmod 0700 .ssh
    ssh-keygen -q -t ed25519 -N "" -C pi4-emulator -f .ssh/id_ed25519
fi
test -f .ssh/id_ed25519.pub

IMAGE="$(cat config/image)"
mkdir -p logs
LOG_FILE="$(mktemp "logs/boot-$(date +%Y%m%d-%H%M%S)-XXXXXX.log")"
ln -sfn "${LOG_FILE##*/}" logs/latest.log
mkdir -p board

# Mount only runtime data and the public key. SSH stays on localhost.
echo "Booting. Use ./logs.sh for the console and ./run.sh to upload and run cFS."
exec docker run --rm "${MODE[@]}" --name pi4-cfs \
    --user "$(id -u):$(id -g)" \
    -p 127.0.0.1:2222:2222 \
    -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro \
    -v "$PWD/board:/work/board" -v "$PWD/logs:/work/logs" \
    -v "$PWD/.ssh/id_ed25519.pub:/ssh.pub:ro" \
    "$IMAGE" "/work/$LOG_FILE"
