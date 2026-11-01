#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Ask Linux to flush the persistent disk and power off normally.
exec ssh -T -o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 \
    -F "$HOME/.ssh/cfs-emulator/config" pi4-cfs systemctl poweroff --no-block
