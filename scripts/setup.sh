#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ((EUID == 0)); then
    echo "Run ./scripts/setup.sh as your normal user; it requests sudo when needed." >&2
    exit 1
fi

# Install missing tools from the system's configured package repositories.
PACKAGES=()
command -v docker >/dev/null || PACKAGES+=(docker.io)
if ! docker buildx version >/dev/null 2>&1; then
    if dpkg-query -s docker-ce-cli >/dev/null 2>&1; then
        PACKAGES+=(docker-buildx-plugin)
    else
        PACKAGES+=(docker-buildx)
    fi
fi
if ! command -v ssh >/dev/null || ! command -v scp >/dev/null || ! command -v ssh-keygen >/dev/null; then
    PACKAGES+=(openssh-client)
fi
if ((${#PACKAGES[@]})); then
    sudo apt-get update
    sudo apt-get install -y "${PACKAGES[@]}"
fi

# A newly added Docker group takes effect after signing in again.
SUDO=()
if ! docker info >/dev/null 2>&1; then
    if ! sudo docker info >/dev/null 2>&1; then
        sudo systemctl enable --now docker
    fi
    sudo groupadd -f docker
    sudo usermod -aG docker "$(id -un)"
    SUDO=(sudo)
fi

# Keep this machine's SSH credentials outside the repository.
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
EOF
chmod 0600 "$SSH_DIR/config" "$SSH_DIR/id_ed25519"

# Reuse the image, download it, or build locally if no published image is available.
IMAGE="$(cat config/image)"
if ! "${SUDO[@]}" docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Downloading the emulator image..."
    if ! "${SUDO[@]}" docker pull "$IMAGE"; then
        echo "Image download failed. Building locally; this can take several minutes..."
        "${SUDO[@]}" ./scripts/build.sh --network=host
    fi
fi

echo "Setup complete. SSH is configured in $SSH_DIR."
if ((${#SUDO[@]})); then
    echo "Sign out and sign in again, then run ./boot.sh."
else
    echo "Next: ./boot.sh"
fi
