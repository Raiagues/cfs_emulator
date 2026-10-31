#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Use the fixed ARM64 build directory in this repository.
if (($#)); then
    echo "Usage: ./run.sh" >&2
    exit 2
fi
PAYLOAD=cFS/build-rpi_linux/exe/cpu1
if [[ ! -f "$PAYLOAD/core-cpu1" || ! -d "$PAYLOAD/cf" ]]; then
    echo "Expected core-cpu1 and cf in $PAYLOAD." >&2
    exit 1
fi
SSH_CONFIG="$HOME/.ssh/cfs-emulator/config"
if [[ ! -f "$SSH_CONFIG" ]]; then
    echo "Run ./scripts/setup.sh first." >&2
    exit 1
fi

echo "Checking the build and virtual sensors..."
python3 project/manage.py check-build
python3 sensors/runtime.py prepare

echo "Stopping cFS..."
ssh -F "$SSH_CONFIG" pi4-cfs systemctl stop cfs.service

# SCP displays transfer progress in the terminal. Stop on any upload error.
echo "Uploading core-cpu1 and cf..."
scp -F "$SSH_CONFIG" -rp "$PAYLOAD/core-cpu1" "$PAYLOAD/cf" \
    pi4-cfs:/opt/cFS/build-rpi_linux/exe/cpu1/

echo "Starting cFS. Ctrl+C stops following the log; cFS keeps running."
ssh -F "$SSH_CONFIG" pi4-cfs systemctl start cfs.service
exec ssh -F "$SSH_CONFIG" pi4-cfs journalctl -u cfs.service -n 30 -f
