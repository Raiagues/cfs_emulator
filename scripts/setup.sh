#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ((EUID == 0)); then
    echo "Run ./scripts/setup.sh as your normal user; it requests sudo when needed." >&2
    exit 1
fi

# Use the supported distribution's packages without replacing working tools.
. /etc/os-release
case "$ID" in
    ubuntu) MIN_RELEASE=24.04 ;;
    debian) MIN_RELEASE=13 ;;
    *) echo "Setup supports Ubuntu 24.04+ and Debian 13+." >&2; exit 1 ;;
esac
if ! dpkg --compare-versions "$VERSION_ID" ge "$MIN_RELEASE" || \
    [[ "$(dpkg --print-architecture)" != amd64 ]]; then
    echo "Setup requires Ubuntu 24.04+ or Debian 13+, on AMD64." >&2
    exit 1
fi

# Docker 23 uses Buildx by default. SSH must support automatic host-key enrollment.
SUDO=()
docker_current() {
    local version
    version="$(docker version --format '{{.Client.Version}}' 2>/dev/null || true)"
    [[ -n "$version" ]] && dpkg --compare-versions "$version" ge 23.0
}
buildx_current() {
    local version
    version="$("${SUDO[@]}" docker buildx version 2>/dev/null | awk '{sub(/^v/, "", $2); print $2}' || true)"
    [[ -n "$version" ]] && dpkg --compare-versions "$version" ge 0.10
}
ssh_current() {
    command -v scp >/dev/null && command -v ssh-keygen >/dev/null && \
        ssh -G -F /dev/null -o StrictHostKeyChecking=accept-new localhost >/dev/null 2>&1
}

echo "[1/4] Checking Docker, Buildx and OpenSSH..."
DOCKER_PACKAGES=(docker.io)
BUILDX_PACKAGE=docker-buildx
if [[ "$(dpkg-query -W -f='${Status}' docker-ce-cli 2>/dev/null)" == 'install ok installed' ]]; then
    DOCKER_PACKAGES=(docker-ce docker-ce-cli)
    BUILDX_PACKAGE=docker-buildx-plugin
elif [[ "$(dpkg-query -W -f='${Status}' docker-buildx-plugin 2>/dev/null)" == 'install ok installed' ]]; then
    BUILDX_PACKAGE=docker-buildx-plugin
fi
PACKAGES=()
docker_current || PACKAGES+=("${DOCKER_PACKAGES[@]}")
buildx_current || PACKAGES+=("$BUILDX_PACKAGE")
ssh_current || PACKAGES+=(openssh-client)
command -v git >/dev/null || PACKAGES+=(git)
command -v python3 >/dev/null || PACKAGES+=(python3)
if ((${#PACKAGES[@]})); then
    sudo apt-get update
    sudo apt-get install -y "${PACKAGES[@]}"
fi
if ! docker_current || ! buildx_current || ! ssh_current; then
    echo "Dependency check failed after installation: Docker >=23, Buildx >=0.10 and OpenSSH with accept-new are required." >&2
    exit 1
fi

# A newly added Docker group takes effect after signing in again.
if ! docker info >/dev/null 2>&1; then
    if ! sudo docker info >/dev/null 2>&1; then
        if ! command -v dockerd >/dev/null; then
            sudo apt-get update
            sudo apt-get install -y "${DOCKER_PACKAGES[@]}"
        fi
        sudo systemctl enable --now docker
    fi
    sudo groupadd -f docker
    sudo usermod -aG docker "$(id -un)"
    SUDO=(sudo)
fi
if ! dpkg --compare-versions "$("${SUDO[@]}" docker version --format '{{.Server.Version}}')" ge 23.0; then
    sudo apt-get update
    sudo apt-get install -y "${DOCKER_PACKAGES[@]}"
fi
if ! dpkg --compare-versions "$("${SUDO[@]}" docker version --format '{{.Server.Version}}')" ge 23.0; then
    echo "The installed Docker engine is still older than version 23." >&2
    exit 1
fi
# sudo uses its own Docker plugins, which may differ from the user's plugins.
if ! buildx_current; then
    sudo apt-get update
    sudo apt-get install -y "$BUILDX_PACKAGE"
fi
if ! buildx_current; then
    echo "Buildx >=0.10 is required for the selected Docker user." >&2
    exit 1
fi
"${SUDO[@]}" docker version --format 'Docker client {{.Client.Version}}, engine {{.Server.Version}}'
"${SUDO[@]}" docker buildx inspect --bootstrap >/dev/null
"${SUDO[@]}" docker buildx version
ssh -V

# Initialize missing submodules over HTTPS, including nested GitHub repositories.
echo "[2/4] Checking repository dependencies..."
SUBMODULES="$(git submodule status --recursive)"
if grep -q '^-' <<< "$SUBMODULES"; then
    git -c url.https://github.com/.insteadOf=git@github.com: submodule update --init --recursive --progress
else
    echo "Repository dependencies are already present."
fi

# Keep this machine's SSH credentials outside the repository.
echo "[3/4] Configuring the local SSH identity..."
SSH_DIR="$HOME/.ssh/cfs-emulator"
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
cat > "$SSH_DIR/config" <<'EOF'
Host pi4-cfs
    HostName 127.0.0.1
    Port 2222
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
echo "[4/4] Preparing the emulator image..."
IMAGE="$(cat config/image)"
if ! "${SUDO[@]}" docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Downloading the emulator image..."
    if ! "${SUDO[@]}" docker pull "$IMAGE"; then
        echo "Image download failed. Building locally; this can take several minutes..."
        "${SUDO[@]}" ./scripts/build.sh --network=host
    fi
else
    echo "Using the installed emulator image."
fi

if [[ "$("${SUDO[@]}" docker image inspect --format '{{index .Config.Labels "org.flight-studio.qemu-lsm-signed"}}' "$IMAGE")" != 1 ]]; then
    echo "Updating the emulator's signed sensor support..."
    "${SUDO[@]}" ./scripts/build.sh --network=host
fi

echo "Setup complete. SSH is configured in $SSH_DIR."
if ((${#SUDO[@]})); then
    echo "Sign out and sign in again, then run ./boot.sh."
else
    echo "Next: ./boot.sh"
fi
