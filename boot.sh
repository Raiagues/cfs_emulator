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

# Setup owns dependencies and SSH credentials, outside the repository.
SSH_DIR="$HOME/.ssh/cfs-emulator"
if [[ ! -f "$SSH_DIR/config" || ! -f "$SSH_DIR/id_ed25519.pub" ]]; then
    echo "Run ./scripts/setup.sh first." >&2
    exit 1
fi

IMAGE="$(cat config/image)"
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Run ./scripts/setup.sh first to prepare Docker and the emulator image." >&2
    exit 1
fi
mkdir -p logs
LOG_FILE="$(mktemp "logs/boot-$(date +%Y%m%d-%H%M%S)-XXXXXX.log")"
ln -sfn "${LOG_FILE##*/}" logs/latest.log
mkdir -p board

# Mount only runtime data and the public key. SSH stays on localhost.
echo "Booting Raspberry Pi OS. Follow its progress with ./logs.sh."
docker run --rm "${MODE[@]}" --name pi4-cfs \
    --user "$(id -u):$(id -g)" \
    -p 127.0.0.1:2222:2222 \
    -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro \
    -v "$PWD/board:/work/board" -v "$PWD/logs:/work/logs" \
    -v "$SSH_DIR/id_ed25519.pub:/ssh.pub:ro" \
    "$IMAGE" "/work/$LOG_FILE"

if [[ "${1:-}" == --interactive ]]; then
    exit 0
fi

# A complete SSH login confirms readiness, including authentication.
echo "Waiting for Linux and SSH. The first boot can take several minutes..."
SSH_DEADLINE=$((SECONDS + 600))
until SSH_ERROR="$(LC_ALL=C ssh -F "$SSH_DIR/config" -o ConnectTimeout=3 pi4-cfs true 2>&1)"; do
    case "$SSH_ERROR" in
        *"Permission denied"*|*"Host key verification failed"*)
            printf '%s\n' "$SSH_ERROR" >&2
            exit 1 ;;
    esac
    if ((SECONDS >= SSH_DEADLINE)) || \
        [[ "$(docker inspect --format '{{.State.Running}}' pi4-cfs 2>/dev/null)" != true ]]; then
        printf '%s\n' "$SSH_ERROR" >&2
        echo "Linux did not become ready. Check ./logs.sh and logs/latest.log." >&2
        exit 1
    fi
    sleep 1
done
echo "Raspberry Pi ready. Run ./run.sh to upload and start cFS."
