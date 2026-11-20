#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Show boot logs by default; attach a guest terminal only when requested.
MODE=(-d)
case "${1:-}" in
    "") ;;
    --interactive) MODE=(-dit) ;;
    *) echo "Usage: ./boot.sh [--interactive]" >&2; exit 2 ;;
esac

# Setup owns dependencies and SSH credentials, outside the repository.
SSH_DIR=$(python3 -m project.defaults keys)
STUDIO_CONTAINER=$(python3 -m project.defaults container)
STUDIO_LISTEN=$(python3 -m project.defaults loopback)
STUDIO_SSH_INTERNAL=$(python3 -m project.defaults internal_ssh)
STUDIO_QMP_INTERNAL=$(python3 -m project.defaults internal_qmp)
STUDIO_QMP_HOST=$(python3 -m project.defaults qmp)
STUDIO_CI_HOST=$(python3 -m project.defaults command)
STUDIO_CI_GUEST=$(python3 -m hardware.infrastructure flight-command)
STUDIO_PLATFORM=$(python3 -m project.defaults platform)
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
if [[ "$(docker image inspect --format '{{index .Config.Labels "org.flight-studio.register-models"}}' "$IMAGE")" != "$(python3 project/qemu/generate.py --fingerprint)" ]]; then
    echo "Install the updated emulator image in workspace setup to load this project's register models." >&2
    exit 1
fi
case "$(docker container inspect --format '{{.State.Running}}' "$STUDIO_CONTAINER" 2>/dev/null)" in
    true)
        echo "The emulator is already running. Use ./start --no-ui run or emulator stop." >&2
        exit 1 ;;
    false)
        owner=$(docker inspect --format '{{index .Config.Labels "org.flight-studio.workspace"}}' "$STUDIO_CONTAINER")
        [[ "$owner" == "$PWD" ]] || { echo "Container name is already in use by another checkout." >&2; exit 1; }
        docker rm "$STUDIO_CONTAINER" >/dev/null ;;
esac
mkdir -p logs
LOG_FILE="$(mktemp "logs/boot-$(date +%Y%m%d-%H%M%S)-XXXXXX.log")"
ln -sfn "${LOG_FILE##*/}" logs/latest.log
mkdir -p board

# Read current project hardware without rebuilding the emulator image.
BOOT_TIMEOUT=600
if [[ ! -f board/raspios.qcow2 ]]; then BOOT_TIMEOUT=1800; fi
echo "[emulator] Image ready. Opening the guest disk."
export STUDIO_SSH_INTERNAL STUDIO_QMP_INTERNAL STUDIO_CI_GUEST
docker run --platform "$STUDIO_PLATFORM" "${MODE[@]}" --name "$STUDIO_CONTAINER" --label "org.flight-studio.workspace=$PWD" \
    --user "$(id -u):$(id -g)" \
    -e STUDIO_SSH_INTERNAL -e STUDIO_QMP_INTERNAL -e STUDIO_CI_GUEST \
    -p "$STUDIO_LISTEN:$STUDIO_QMP_HOST:$STUDIO_QMP_INTERNAL/tcp" \
    -p "$STUDIO_LISTEN:$STUDIO_CI_HOST:$STUDIO_CI_GUEST/udp" \
    -p "$STUDIO_LISTEN:$EMULATOR_SSH_PORT:$STUDIO_SSH_INTERNAL" \
    -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro \
    -v "$PWD/board:/work/board" -v "$PWD/logs:/work/logs" \
    -v "$PWD/project:/work/project:ro" -v "$PWD/sensors:/work/sensors:ro" \
    -v "$PWD/scripts/emulator.sh:/usr/local/bin/emulator:ro" \
    -v "$SSH_DIR/id_ed25519.pub:/ssh.pub:ro" \
    "$IMAGE" "/work/$LOG_FILE"

if [[ "${1:-}" == --interactive ]]; then
    # Keep the serial console interactive while this disk's sshd starts.
    nohup python3 -m hardware.emulator_ssh wait "$BOOT_TIMEOUT" \
        </dev/null >"${LOG_FILE%.log}-ssh.log" 2>&1 &
    exec docker attach "$STUDIO_CONTAINER"
fi

# Follow the boot output while checking that Linux accepts this machine's SSH key.
docker logs --follow "$STUDIO_CONTAINER" &
LOG_PID=$!
stop_logs() {
    kill "$LOG_PID" 2>/dev/null || true
    wait "$LOG_PID" 2>/dev/null || true
}
trap stop_logs EXIT
trap 'echo "Boot continues in the background. Use ./logs.sh to follow it."; exit 130' INT
trap 'exit 143' TERM

python3 -m hardware.emulator_ssh wait "$BOOT_TIMEOUT"
stop_logs
trap - EXIT
python3 sensors/runtime.py values
printf '\nRaspberry Pi ready. Run ./start --no-ui run --target qemu to start cFS.\n'
