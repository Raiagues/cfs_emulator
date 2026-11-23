#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Close this workspace's Studio server. Target operations use ./start --no-ui.
exec python3 -m interface.lifecycle "$@"
