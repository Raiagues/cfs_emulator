#!/usr/bin/env bash

# Include first-run preparation and the serial console; Ctrl+C leaves QEMU running.
exec docker logs --follow pi4-cfs
