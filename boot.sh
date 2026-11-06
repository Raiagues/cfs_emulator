#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Show boot logs by default; attach a guest terminal only when requested.
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

IMAGE="$(python3 -m hardware.infrastructure image)"
EMULATOR_SSH_PORT="$(python3 -m hardware.infrastructure ssh_port)"
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Run ./scripts/setup.sh first to prepare Docker and the emulator image." >&2
    exit 1
fi
if docker container inspect pi4-cfs >/dev/null 2>&1; then
    echo "The emulator is already running. Use ./run.sh or ./stop.sh." >&2
    exit 1
fi
mkdir -p logs
LOG_FILE="$(mktemp "logs/boot-$(date +%Y%m%d-%H%M%S)-XXXXXX.log")"
ln -sfn "${LOG_FILE##*/}" logs/latest.log
mkdir -p board

# Read current project hardware without rebuilding the emulator image.
echo "Booting Raspberry Pi OS..."
docker run --rm "${MODE[@]}" --name pi4-cfs \
    --user "$(id -u):$(id -g)" \
    -p "127.0.0.1:$EMULATOR_SSH_PORT:2222" \
    -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro \
    -v "$PWD/board:/work/board" -v "$PWD/logs:/work/logs" \
    -v "$PWD/project:/work/project:ro" -v "$PWD/sensors:/work/sensors:ro" \
    -v "$PWD/scripts/emulator.sh:/usr/local/bin/emulator:ro" \
    -v "$SSH_DIR/id_ed25519.pub:/ssh.pub:ro" \
    "$IMAGE" "/work/$LOG_FILE"

if [[ "${1:-}" == --interactive ]]; then
    exit 0
fi

# Follow the boot output while checking that Linux accepts this machine's SSH key.
docker logs --follow pi4-cfs &
LOG_PID=$!
stop_logs() {
    kill "$LOG_PID" 2>/dev/null || true
    wait "$LOG_PID" 2>/dev/null || true
}
trap stop_logs EXIT
trap 'echo "Boot continues in the background. Use ./logs.sh to follow it."; exit 130' INT
trap 'exit 143' TERM

SSH_DEADLINE=$((SECONDS + 600))
NEXT_STATUS=0
until SSH_ERROR="$(LC_ALL=C ssh -F "$SSH_DIR/config" -p "$EMULATOR_SSH_PORT" -o ConnectTimeout=3 pi4-cfs true 2>&1)"; do
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
    if ((SECONDS >= NEXT_STATUS)); then
        printf '\n[Boot: %ss] SSH check: %s\n' "$SECONDS" "${SSH_ERROR##*$'\n'}"
        NEXT_STATUS=$((SECONDS + 10))
    fi
    sleep 1
done
stop_logs
trap - EXIT
python3 sensors/runtime.py values
printf '\nRaspberry Pi ready. Run ./run.sh to upload and start cFS.\n'
