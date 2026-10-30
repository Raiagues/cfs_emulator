#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Accept an existing ARM64 build; this script does not compile cFS.
PAYLOAD="${1:-cFS/build-rpi_linux/exe/cpu1}"
if [[ ! -f "$PAYLOAD/core-cpu1" || ! -d "$PAYLOAD/cf" ]]; then
    echo "Expected core-cpu1 and cf in $PAYLOAD." >&2
    exit 1
fi
# Docker can open the port before Linux is ready; wait for a complete SSH login.
echo "Waiting for SSH..."
SSH_DEADLINE=$((SECONDS + 300))
until ssh -F config/ssh.conf -o ConnectTimeout=3 pi4-cfs true 2>/dev/null; do
    if ((SECONDS >= SSH_DEADLINE)) || \
        [[ "$(docker inspect --format '{{.State.Running}}' pi4-cfs 2>/dev/null)" != true ]]; then
        echo "SSH is unavailable. Check ./logs.sh and ./boot.sh." >&2
        exit 1
    fi
    sleep 1
done

echo "Stopping cFS..."
ssh -F config/ssh.conf pi4-cfs systemctl stop cfs.service

# SCP displays transfer progress in the terminal. Stop on any upload error.
echo "Uploading core-cpu1 and cf..."
scp -F config/ssh.conf -rp "$PAYLOAD/core-cpu1" "$PAYLOAD/cf" \
    pi4-cfs:/opt/cFS/build-rpi_linux/exe/cpu1/

echo "Starting cFS. Ctrl+C stops following the log; cFS keeps running."
ssh -F config/ssh.conf pi4-cfs systemctl start cfs.service
exec ssh -F config/ssh.conf pi4-cfs journalctl -u cfs.service -n 30 -f
