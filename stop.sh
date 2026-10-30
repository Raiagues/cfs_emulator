#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Ask Linux to flush the persistent disk and power off normally.
exec ssh -F "$HOME/.ssh/cfs-emulator/config" pi4-cfs systemctl poweroff
