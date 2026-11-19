#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Ask Linux to flush the persistent disk and power off normally.
exec python3 -m hardware.emulator_ssh ssh systemctl poweroff --no-block
