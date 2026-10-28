#!/usr/bin/env bash
# Import the reference image into headless Ghidra, seed the disassembly, export Kick Assembler source into the landing zone (GHIDRA_EXPORT_DIR).
# This NEVER touches phase1/src: the canonical source is hand-edited from the first seeding on (the never-edit-both rule).
#
#   run.sh [PROJECT_ROOT]       project.config keys: PROJECT_NAME, REFERENCE_PRG, LOAD_ADDRESS (hex, e.g. 0x0800), GHIDRA_EXPORT_DIR (default ghidra),
#                               GHIDRA_HOME (else ~/ghidra*/ghidra_*), GHIDRA_SEEDS / GHIDRA_LABELS / GHIDRA_HOLES (default tools/ghidra/seeds.txt, labels.txt, holes.txt),
#                               GHIDRA_PROCESSOR (default 6502:LE:16:default)
set -euo pipefail
ROOT="$(cd "${1:-.}" && pwd)"; cd "$ROOT"; HERE="$(cd "$(dirname "$0")" && pwd)"
source ./project.config
GH="${GHIDRA_HOME:-$(ls -d "$HOME"/ghidra*/ghidra_* 2>/dev/null | grep -v zip | head -1)}"
[ -x "$GH/support/analyzeHeadless" ] || { echo "Ghidra not found: set GHIDRA_HOME (project.config or environment)"; exit 1; }
OUT="${GHIDRA_EXPORT_DIR:-ghidra}"; NAME="${PROJECT_NAME:-project}"
SEEDS="${GHIDRA_SEEDS:-tools/ghidra/seeds.txt}"; LABELS="${GHIDRA_LABELS:-tools/ghidra/labels.txt}"; HOLES="${GHIDRA_HOLES:-tools/ghidra/holes.txt}"
[ -f "$SEEDS" ] || { echo "no seeds file $SEEDS (scripts/ghidra/make_seeds.py writes one)"; exit 1; }
mkdir -p "$OUT"
# remove only this project's previous Ghidra project files; ${VAR:?} stops the shell if a name is empty
rm -rf "${OUT:?}/${NAME:?}.rep" "${OUT:?}/${NAME:?}.gpr"
"$GH/support/analyzeHeadless" "$ROOT/$OUT" "$NAME" -import "$ROOT/$REFERENCE_PRG" \
    -processor "${GHIDRA_PROCESSOR:-6502:LE:16:default}" -loader BinaryLoader -loader-baseAddr "${LOAD_ADDRESS:-0x0800}" -overwrite \
    -scriptPath "$HERE" -postScript setup.py "$ROOT/$SEEDS" "$ROOT/$LABELS" "$ROOT/$HOLES" "$ROOT/$OUT" 2>&1 | grep -E "Export Complete|ERROR|Exception|Traceback|seeded|File|\.asm" || true
ls -la "$OUT"
