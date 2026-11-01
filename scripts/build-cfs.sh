#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

AS_USER=()
if [[ -n "${SUDO_USER:-}" ]]; then
    AS_USER=(sudo -u "$SUDO_USER")
fi

MISSION_TARGET="${2:-}"
if [[ $# -gt 0 && ( $# -ne 2 || "$1" != "--target" ) ]]; then
    echo "Usage: scripts/build-cfs.sh [--target native|qemu|physical]" >&2
    exit 2
fi
if [[ -z "$MISSION_TARGET" ]]; then
    MISSION_TARGET=$(python3 -c 'import json; c=json.load(open("project/config.json")); print("native" if c.get("board") is None else "qemu")')
fi
case "$MISSION_TARGET" in
    native) MISSION_PROFILE=native ;;
    qemu|physical) MISSION_PROFILE=flight ;;
    *) echo "Invalid build target: $MISSION_TARGET" >&2; exit 2 ;;
esac

"${AS_USER[@]}" python3 project/manage.py sync
MISSION_ARCH=$(python3 -c 'from pathlib import Path; from project.cfs_config import build_profile; print(build_profile(Path.cwd())["architecture"])')
if [[ ! "$MISSION_ARCH" =~ ^[a-zA-Z0-9_-]+$ ]] || [[ "$MISSION_PROFILE" == native && "$MISSION_ARCH" != native ]] || [[ "$MISSION_PROFILE" == flight && "$MISSION_ARCH" == native ]]; then
    echo "Select the matching native or board/OS profile before building." >&2
    exit 1
fi
MISSION_BUILD="build-$MISSION_PROFILE"
MAKE_OPTIONS=(
    -j4 CONFIG_NAMES=studio CFS_CONFIG_NAMES=studio
    "O_studio=$MISSION_BUILD/cache" "ARCH_studio=$MISSION_ARCH"
    "PREP_OPTS_studio=-DSIMULATION=$MISSION_ARCH -DMISSIONCONFIG=sample -DCFE_EDS_ENABLED=OFF -DENABLE_UNIT_TESTS=OFF"
    BUILDTYPE=release studio.prep studio.install
)

# CMake install does not remove modules that were removed from APPLIST.
"${AS_USER[@]}" rm -rf -- "cFS/$MISSION_BUILD/exe"
if [[ "$MISSION_TARGET" == native ]]; then
    "${AS_USER[@]}" make -C "$PWD/cFS" "DESTDIR=$PWD/cFS/$MISSION_BUILD" "${MAKE_OPTIONS[@]}"
else
    docker build --network=host --target cfs-builder -t cfs-builder:local .
    docker run --rm --user "${SUDO_UID:-$(id -u)}:${SUDO_GID:-$(id -g)}" \
        -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro \
        -v "$PWD/cFS:/cFS" cfs-builder:local \
        make "DESTDIR=/cFS/$MISSION_BUILD" "${MAKE_OPTIONS[@]}"
fi
"${AS_USER[@]}" python3 project/manage.py stamp --target "$MISSION_TARGET"
echo "Build ready: cFS/$MISSION_BUILD/exe/cpu1"
