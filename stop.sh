#!/usr/bin/env bash
set -e

# Ask Linux to flush the persistent disk and power off normally.
exec ssh -p 2222 root@127.0.0.1 systemctl poweroff
