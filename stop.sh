#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Ask Linux to flush the persistent disk and power off normally.
exec ssh -F config/ssh.conf pi4-cfs systemctl poweroff
