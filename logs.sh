#!/usr/bin/env bash

# Follow the latest run from the beginning; Ctrl+C leaves QEMU running.
exec tail -n +1 -F "$(dirname "$0")/logs/latest.log"
