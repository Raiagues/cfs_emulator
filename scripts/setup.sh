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
SUDO=()
version_at_least() {
    python3 -c 'import re,sys
m = re.search(r"(\d+)\.(\d+)", sys.argv[1])
sys.exit(0 if m and tuple(map(int, m.groups())) >= tuple(map(int, sys.argv[2:])) else 1)' "$@"
}

docker_current() {
    version_at_least "$(docker --version 2>/dev/null)" 23 0
}
buildx_current() {
    version_at_least "$("${SUDO[@]}" docker buildx version 2>/dev/null)" 0 10
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
if ! docker info >/dev/null 2>&1; then
    if ! sudo docker info >/dev/null 2>&1; then
        sudo systemctl enable --now docker
    fi
    sudo groupadd -f docker
    sudo usermod -aG docker "$(id -un)"
    SUDO=(sudo)
fi
if ! version_at_least "$("${SUDO[@]}" docker version --format '{{.Server.Version}}')" 23 0 || ! buildx_current || ! ssh_current; then
    echo "Docker Engine 23+, Buildx 0.10+ and OpenSSH are required for board builds." >&2
    exit 1
fi
"${SUDO[@]}" docker version --format 'Docker client {{.Client.Version}}, engine {{.Server.Version}}'
echo "Verifying the build worker..."
"${SUDO[@]}" docker buildx inspect --bootstrap >/dev/null
"${SUDO[@]}" docker buildx version
ssh -V

if [[ "${1:-}" == --build-only ]]; then
    echo "Build tools ready. Connect the board from Infrastructure."
    exit 0
fi

# Keep this machine's SSH credentials outside the repository.
echo "Configuring the local SSH identity..."
SSH_DIR="$HOME/.ssh/cfs-emulator"
EMULATOR_SSH_PORT="$(python3 -m hardware.infrastructure ssh_port)"
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
cat > "$SSH_DIR/config" <<EOF
Host pi4-cfs
    HostName 127.0.0.1
    Port $EMULATOR_SSH_PORT
    User root
    IdentityFile ~/.ssh/cfs-emulator/id_ed25519
    IdentitiesOnly yes
    UserKnownHostsFile ~/.ssh/cfs-emulator/known_hosts
    StrictHostKeyChecking accept-new
    BatchMode yes
    ConnectTimeout 5
EOF
chmod 0600 "$SSH_DIR/config" "$SSH_DIR/id_ed25519"

# Reuse the image, download it, or build locally if no published image is available.
echo "Preparing the emulator image..."
IMAGE="$(python3 -m hardware.infrastructure image)"
if ! "${SUDO[@]}" docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Downloading the emulator image..."
    if ! "${SUDO[@]}" docker pull "$IMAGE"; then
        echo "Image download failed. Building locally; this can take several minutes..."
        "${SUDO[@]}" ./scripts/build.sh --network=host
    fi
else
    echo "Using the installed emulator image."
fi

if [[ "$("${SUDO[@]}" docker image inspect --format '{{index .Config.Labels "org.flight-studio.register-models"}}' "$IMAGE")" != "$(python3 project/qemu/generate.py --fingerprint)" ]]; then
    echo "Building the configured sensor models..."
    "${SUDO[@]}" ./scripts/build.sh --network=host
fi

echo "Setup complete. SSH is configured in $SSH_DIR."
if ((${#SUDO[@]})); then
    echo "Sign out and sign in again, then run ./boot.sh."
else
    echo "Next: ./boot.sh"
fi
