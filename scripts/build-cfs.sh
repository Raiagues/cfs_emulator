#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Setup may need sudo for Docker; keep generated files owned by the user.
AS_USER=()
if [[ -n "${SUDO_USER:-}" ]]; then
    AS_USER=(sudo -u "$SUDO_USER")
fi

# Keep the container's CMake cache separate; install binaries in the fixed directory.
echo "Synchronizing apps and sensor bindings..."
"${AS_USER[@]}" python3 project/manage.py sync
echo "Preparing the cFS cross-compiler..."
docker build --network=host --target cfs-builder -t cfs-builder:local .
echo "Compiling cFS for Raspberry Pi OS..."
docker run --rm --user "${SUDO_UID:-$(id -u)}:${SUDO_GID:-$(id -g)}" \
    -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro \
    -v "$PWD/cFS:/cFS" cfs-builder:local
"${AS_USER[@]}" python3 project/manage.py stamp
echo "ARM64 build ready: cFS/build-rpi_linux/exe/cpu1. Run ./run.sh to upload it."
