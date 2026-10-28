#!/usr/bin/env bash
# framework/scripts/launch.sh
# Experiment-build (no diff) then drop into an emulator with symbols loaded, so
# the debugger shows your labels not raw addresses. Two surfaces:
#   vice   -> VICE x64, fast, VICE monitor for scripted checks  (default)
#   retro  -> RetroDebugger, better for visual/sprite work
#
# Optional pokes file: a JSON array of {addr, val, comment} objects. Each entry
# is patched into a temporary copy of the PRG before launch, leaving the build
# artefact untouched.  Addresses must be in PRG space ($080E–$FF72).
#
# Usage:
#   launch.sh                            # VICE, no patches
#   launch.sh vice                       # explicit
#   launch.sh vice pokes/room_0d.json    # VICE with pokes applied
#   launch.sh retro                      # RetroDebugger, no patches
#   launch.sh retro pokes/room_0d.json   # RetroDebugger with pokes applied

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$PROJECT_ROOT"

# shellcheck disable=SC1091
source ./project.config

TARGET="${1:-vice}"
POKES_FILE="${2:-}"

# Experiment build: assemble whatever's currently in source, no verify gate.
# Byte-identity is allowed to be broken here by design.
PROJECT_ROOT="$PROJECT_ROOT" bash framework/scripts/build.sh

# Resolve the PRG to launch — either the built artifact or a patched copy.
LAUNCH_PRG="$OUTPUT_PRG"
TEMP_PRG=""

if [ -n "$POKES_FILE" ]; then
    if [ ! -f "$POKES_FILE" ]; then
        echo "!! pokes file not found: $POKES_FILE" >&2
        exit 1
    fi
    TEMP_PRG=$(mktemp /tmp/c64decomp_poked_XXXXXX.prg)
    cp "$OUTPUT_PRG" "$TEMP_PRG"
    echo ">> applying pokes from $POKES_FILE"
    python3 framework/scripts/apply_pokes.py "$POKES_FILE" "$TEMP_PRG" "$LOAD_ADDRESS"
    LAUNCH_PRG="$TEMP_PRG"
fi

case "$TARGET" in
  vice)
    if [ ! -x "$VICE_BIN" ]; then
        echo "!! VICE not executable at $VICE_BIN" >&2
        exit 1
    fi
    if [ "${LAUNCH_MODE:-sys}" = "snapshot" ]; then
        # Image cannot be started with a typed SYS: inject it, restore the
        # hardware state and resume at the entry point (see project.config).
        echo ">> launching VICE with snapshot injection${POKES_FILE:+ (poked PRG)}"
        python3 framework/scripts/vice_snapshot_launch.py --vice "$VICE_BIN" \
            --spec "$SNAPSHOT_SPEC" --prg "$LAUNCH_PRG" --symbols "$VICE_SYMBOLS"
    else
        echo ">> launching VICE x64 with symbols${POKES_FILE:+ (poked PRG)}"
        "$VICE_BIN" -moncommands "$VICE_SYMBOLS" -keybuf "sys 2064\x0d" "$LAUNCH_PRG"
    fi
    ;;
  retro)
    if [ ! -x "$RETRODEBUGGER_BIN" ]; then
        echo "!! RetroDebugger not executable at $RETRODEBUGGER_BIN" >&2
        exit 1
    fi
    echo ">> launching RetroDebugger with symbols${POKES_FILE:+ (poked PRG)}"
    "$RETRODEBUGGER_BIN" -c64 "$LAUNCH_PRG" -debuginfo "$DEBUG_FILE" -symbols "$VICE_SYMBOLS" -wait 3000 -jmp x0810 -unpause
    ;;
  *)
    echo "!! unknown launch target '$TARGET' (use: vice | retro)" >&2
    exit 2
    ;;
esac

# Clean up temp PRG if we made one (runs after emulator exits).
if [ -n "$TEMP_PRG" ]; then rm -f "$TEMP_PRG"; fi
