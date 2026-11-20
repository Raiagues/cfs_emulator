#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

AS_USER=()
if [[ -n "${SUDO_USER:-}" ]]; then
    AS_USER=(sudo -u "$SUDO_USER")
fi

MISSION_TARGET="${2:-}"
CHECK_APP=""
if [[ $# -eq 4 && "$3" == --check-app && "$4" =~ ^[a-z][a-z0-9_]{0,18}$ ]]; then
    CHECK_APP="$4"
    set -- "$1" "$2"
fi
if [[ $# -gt 0 && ( $# -ne 2 || "$1" != "--target" ) ]]; then
    echo "Usage: scripts/build-cfs.sh [--target native|qemu|physical [--check-app NAME]]" >&2
    exit 2
fi
if [[ -z "$MISSION_TARGET" ]]; then
    MISSION_TARGET=$(python3 -c 'from hardware.targets import selected_target; print(selected_target(".", required=True))')
fi
case "$MISSION_TARGET" in
    native) MISSION_PROFILE=native ;;
    qemu|physical) MISSION_PROFILE=flight ;;
    *) echo "Invalid build target: $MISSION_TARGET" >&2; exit 2 ;;
esac

if [[ -z "$CHECK_APP" ]]; then
    "${AS_USER[@]}" python3 project/manage.py sync
fi
if [[ "$MISSION_TARGET" == native ]]; then
    MISSION_ARCH=native
else
    MISSION_ARCH=$(python3 -c 'from pathlib import Path; from project.cfs_config import build_profile; print(build_profile(Path.cwd())["architecture"])')
fi
if [[ ! "$MISSION_ARCH" =~ ^[a-zA-Z0-9_-]+$ ]] || [[ "$MISSION_PROFILE" == native && "$MISSION_ARCH" != native ]] || [[ "$MISSION_PROFILE" == flight && "$MISSION_ARCH" == native ]]; then
    echo "Select the matching native or board/OS profile before building." >&2
    exit 1
fi
MISSION_BUILD="build-$MISSION_PROFILE"
BUILD_JOBS=4
if [[ "$MISSION_TARGET" == native ]]; then
    BUILD_JOBS=$(python3 -c 'from hardware.state import RuntimeState; print(RuntimeState(".").build_settings().jobs)')
    [[ "$BUILD_JOBS" =~ ^([1-9]|[1-5][0-9]|6[0-4])$ ]] || { echo "Invalid native build jobs" >&2; exit 1; }
fi
# Use cFE's external mission definitions and module search path on both hosts.
if [[ "$MISSION_TARGET" == native ]]; then
    SOURCE_ROOT="$PWD/cFS"
    MISSION_ROOT="$PWD/mission"
    RUN=("${AS_USER[@]}")
else
    BUILDER_IMAGE=$(python3 -m project.defaults builder)
    BUILDER_PLATFORM=$(python3 -m project.defaults platform)
    docker build --platform "$BUILDER_PLATFORM" --network=host --target cfs-builder -t "$BUILDER_IMAGE" .
    SOURCE_ROOT=/cFS
    MISSION_ROOT=/mission
    RUN=(docker run --platform "$BUILDER_PLATFORM" --rm --user "${SUDO_UID:-$(id -u)}:${SUDO_GID:-$(id -g)}"
         -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro
         -v "$PWD/cFS:/cFS:ro" -v "$PWD/mission:/mission" "$BUILDER_IMAGE")
fi
BUILD_ROOT="$MISSION_ROOT/$MISSION_BUILD"
"${RUN[@]}" cmake -S "$SOURCE_ROOT/cfe" -B "$BUILD_ROOT/cache" \
    "-DMISSION_DEFS=$MISSION_ROOT/sample_defs" "-DCFS_APP_PATH=$SOURCE_ROOT/apps:$SOURCE_ROOT/libs:$MISSION_ROOT/apps:$MISSION_ROOT/libs" \
    "-DSIMULATION=$MISSION_ARCH" -DMISSIONCONFIG=sample -DCFE_EDS_ENABLED=OFF -DENABLE_UNIT_TESTS=OFF \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_BUILD_TYPE=release -DCMAKE_INSTALL_PREFIX=/exe
if [[ -n "$CHECK_APP" ]]; then
    # cFE names its sub-builds from the active toolchain and platform.
    # The generated mission adds a person's app to cpu1 only.
    shopt -s nullglob
    app_dirs=(mission/"$MISSION_BUILD"/cache/*/*/apps/"$CHECK_APP")
    if [[ ${#app_dirs[@]} -ne 1 ]]; then
        echo "cFE did not configure a unique build for $CHECK_APP" >&2
        exit 1
    fi
    cpu_dir=${app_dirs[0]%/apps/*}
    "${RUN[@]}" cmake --build "$MISSION_ROOT/${cpu_dir#mission/}" --parallel "$BUILD_JOBS" --target "$CHECK_APP"
    exit 0
fi
# Install a complete payload so removed modules cannot survive in the deployed image.
"${AS_USER[@]}" rm -rf -- "mission/$MISSION_BUILD/exe"
"${RUN[@]}" env "DESTDIR=$BUILD_ROOT" cmake --build "$BUILD_ROOT/cache" --parallel "$BUILD_JOBS" --target mission-install
"${AS_USER[@]}" python3 project/manage.py stamp --target "$MISSION_TARGET"
echo "Build ready: mission/$MISSION_BUILD/exe/cpu1"
