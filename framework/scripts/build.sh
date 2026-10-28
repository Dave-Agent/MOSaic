#!/usr/bin/env bash
# framework/scripts/build.sh
# Generic KickAssembler invocation. Reads project.config, knows nothing about
# any specific project. Assembles SRC_MAIN to OUTPUT_PRG and emits the VICE
# symbol file and KickAss debug file for the emulator/debugger.
#
# Usage: build.sh [--quiet]
# Expects PROJECT_ROOT in env (set by the justfile) or runs from project root.

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$PROJECT_ROOT"

# shellcheck disable=SC1091
source ./project.config

QUIET="${1:-}"

mkdir -p "$BUILD_DIR"

# KickAssembler flags:
#   -o            output PRG path
#   -vicesymbols  emit VICE-format symbol file (.vs) next to output
#   -debugdump    emit KickAss debug file (.dbg) for RetroDebugger
# KickAss derives .vs/.dbg names from the output basename, so we point -o at
# OUTPUT_PRG and let the sibling files fall out, then confirm they match config.
ASM_CMD=( "$JAVA" -jar "$KICKASS_JAR"
          "$SRC_MAIN"
          -o "$OUTPUT_PRG"
          -odir "$BUILD_DIR"
          -vicesymbols
          -debugdump )

if [ "$QUIET" = "--quiet" ]; then
    "${ASM_CMD[@]}" >/dev/null
else
    echo ">> assembling $SRC_MAIN -> $OUTPUT_PRG"
    "${ASM_CMD[@]}"
fi

if [ ! -f "$OUTPUT_PRG" ]; then
    echo "!! build produced no PRG at $OUTPUT_PRG" >&2
    exit 1
fi
