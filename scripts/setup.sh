#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --build-only ) ]]; then
    echo "Usage: scripts/setup.sh [--build-only]" >&2
    exit 2
fi

if ((EUID == 0)); then
    echo "Run ./scripts/setup.sh as your normal user; it requests sudo when needed." >&2
    exit 1
fi

./scripts/setup-native.sh
version_at_least() {
    python3 -c 'import re,sys
m = re.search(r"(\d+)\.(\d+)", sys.argv[1])
sys.exit(0 if m and tuple(map(int, m.groups())) >= tuple(map(int, sys.argv[2:])) else 1)' "$@"
}

docker_current() {
    version_at_least "$(docker --version 2>/dev/null)" 23 0
}
buildx_current() {
    version_at_least "$(docker buildx version 2>/dev/null)" 0 10
}
ssh_current() {
    command -v scp >/dev/null && command -v ssh-keygen >/dev/null && \
        ssh -G -F /dev/null -o StrictHostKeyChecking=accept-new localhost >/dev/null 2>&1
}

echo "Checking Docker, Buildx and OpenSSH..."
if ! docker_current || ! buildx_current || ! ssh_current; then
    packages=()
    if command -v apt-get >/dev/null; then
        sudo apt-get update
        install=(sudo apt-get install -y)
        engine=docker.io
        plugin=docker-buildx
        client=openssh-client
        if dpkg-query -W -f='${Status}' docker-ce-cli 2>/dev/null | grep -q 'install ok installed'; then
            engine=docker-ce
            plugin=docker-buildx-plugin
        elif ! apt-cache show docker-buildx >/dev/null 2>&1; then
            plugin=docker-buildx-plugin
        fi
    elif command -v dnf >/dev/null; then
        install=(sudo dnf install -y)
        engine=moby-engine
        plugin=docker-buildx
        client=openssh-clients
    elif command -v pacman >/dev/null; then
        install=(sudo pacman -S --needed --noconfirm)
        engine=docker
        plugin=docker-buildx
        client=openssh
    elif command -v zypper >/dev/null; then
        install=(sudo zypper --non-interactive install)
        engine=docker
        plugin=docker-buildx
        client=openssh
    else
        echo "Install Docker Engine 23+, Buildx 0.10+ and OpenSSH, then rerun setup." >&2
        exit 1
    fi
    docker_current || packages+=("$engine")
    buildx_current || packages+=("$plugin")
    ssh_current || packages+=("$client")
    "${install[@]}" "${packages[@]}"
fi

echo "Connecting to Docker Engine..."
if ! engine_status=$(docker info --format '{{.ServerVersion}}' 2>&1); then
    echo "$engine_status" >&2
    if [[ "$engine_status" == *'permission denied'* ]]; then
        echo "Request membership in the docker group, sign in again and rerun setup." >&2
    else
        echo "Start Docker Engine or Docker Desktop and rerun setup." >&2
    fi
    exit 1
fi
if ! version_at_least "$(docker version --format '{{.Server.Version}}')" 23 0 || ! buildx_current || ! ssh_current; then
    echo "Docker Engine 23+, Buildx 0.10+ and OpenSSH are required for board builds." >&2
    exit 1
fi
docker version --format 'Docker client {{.Client.Version}}, engine {{.Server.Version}}'
echo "Verifying the build worker..."
docker buildx inspect --bootstrap >/dev/null
docker buildx version
ssh -V

if [[ "${1:-}" == --build-only ]]; then
    echo "Build tools ready. Connect the board from Infrastructure."
    exit 0
fi

# Generate an independent identity for this checkout.
echo "Configuring the local SSH identity..."
SSH_DIR=$(python3 -m project.defaults keys)
mkdir -p "$SSH_DIR"
chmod 0700 "$SSH_DIR"
if [[ ! -f "$SSH_DIR/id_ed25519" ]]; then
    if [[ -e board/raspios.qcow2 ]]; then
        echo "Restore this guest's key to $SSH_DIR before continuing." >&2
        exit 1
    fi
    ssh-keygen -q -t ed25519 -N "" -C cfs-emulator -f "$SSH_DIR/id_ed25519"
fi
ssh-keygen -y -f "$SSH_DIR/id_ed25519" > "$SSH_DIR/id_ed25519.pub"
config_tmp="$(mktemp "$SSH_DIR/config.XXXXXX")"
trap 'rm -f "$config_tmp"' EXIT
python3 -m hardware.emulator_ssh config > "$config_tmp"
mv "$config_tmp" "$SSH_DIR/config"
trap - EXIT
chmod 0600 "$SSH_DIR/config" "$SSH_DIR/id_ed25519"

echo "Preparing the emulator image..."
./start --no-ui emulator image

echo "Setup complete. SSH is configured in $SSH_DIR."
echo "Next: ./start --no-ui boot --target qemu"
