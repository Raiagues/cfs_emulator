#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

docker build --network=host -t pi4-emulator:dev .
