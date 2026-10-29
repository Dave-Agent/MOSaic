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

# Phase 2 (C64_PHASE=2, set by `just build 2`): the same gate on the split source: PHASE2_MAIN assembled into $BUILD_DIR/p2/game.prg.
if [ "${C64_PHASE:-1}" = "2" ]; then
    [ -n "${PHASE2_MAIN:-}" ] && [ -f "$PHASE2_MAIN" ] || { echo "!! C64_PHASE=2 but PHASE2_MAIN is not set or not a file" >&2; exit 2; }
    SRC_MAIN="$PHASE2_MAIN"; BUILD_DIR="$BUILD_DIR/p2"; OUTPUT_PRG="$BUILD_DIR/game.prg"
fi

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

LOG="$(mktemp)"; trap 'rm -f "$LOG"' EXIT
[ "$QUIET" = "--quiet" ] || echo ">> assembling $SRC_MAIN -> $OUTPUT_PRG"
if ! "${ASM_CMD[@]}" >"$LOG" 2>&1; then
    # quiet mode must not hide WHY the assembly failed: show Kick's error lines
    echo "!! the assembler failed on $SRC_MAIN:" >&2
    { grep -E -B1 -A4 "Error" "$LOG" | head -30; } >&2 || tail -20 "$LOG" >&2
    exit 1
fi
[ "$QUIET" = "--quiet" ] || cat "$LOG"
# Kick exits 0 and still writes the PRG when an .assert fails (it only prints "Made N asserts , M FAILED!"): an assert nobody enforces guards nothing, so a failed one fails the build
if grep -q "asserts.*FAILED" "$LOG"; then
    echo "!! assertion(s) FAILED in $SRC_MAIN:" >&2
    grep -iE "assert" "$LOG" | head -20 >&2
    exit 1
fi

# Kick writes the symbol file next to the source or the output depending on its version: leave one at a fixed place, $BUILD_DIR/game.sym (phase 2: $BUILD_DIR/p2/game.sym),
# which TRACE_SYM / TRACE_SYM_P1 and the trace tools point at.
SYM_NEWEST="$(ls -t "$BUILD_DIR"/*.sym "$(dirname "$SRC_MAIN")"/build/*.sym "$(dirname "$SRC_MAIN")"/build/p2/*.sym 2>/dev/null | grep -v '/game\.sym$' | head -1 || true)"
[ -n "$SYM_NEWEST" ] && cp "$SYM_NEWEST" "$BUILD_DIR/game.sym"

if [ ! -f "$OUTPUT_PRG" ]; then
    echo "!! build produced no PRG at $OUTPUT_PRG" >&2
    exit 1
fi
