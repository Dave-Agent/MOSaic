#!/usr/bin/env bash
# Import the reference image into headless Ghidra, seed the disassembly, export Kick Assembler source into the landing zone (GHIDRA_EXPORT_DIR).
# This NEVER touches phase1/src: the canonical source is hand-edited from the first seeding on (the never-edit-both rule).
#
#   run.sh [PROJECT_ROOT]       project.config keys: PROJECT_NAME, REFERENCE_PRG, LOAD_ADDRESS (hex, e.g. 0x0800), GHIDRA_EXPORT_DIR (default ghidra),
#                               GHIDRA_HOME (else ~/ghidra*/ghidra_*), GHIDRA_SEEDS / GHIDRA_LABELS / GHIDRA_HOLES (default tools/ghidra/seeds.txt, labels.txt, holes.txt),
#                               GHIDRA_PROCESSOR (default 6502:LE:16:default), GHIDRA_EXPORTER (path of KickAssemblerExport.py; else fetched, pinned, into tools/ghidra/exporter/)
set -euo pipefail
ROOT="$(cd "${1:-.}" && pwd)"; cd "$ROOT"; HERE="$(cd "$(dirname "$0")" && pwd)"
source ./project.config
# GHIDRA_HOME, else the newest Ghidra found under ~/ghidra*/ (compared by version, not by the locale's sort order)
GH="${GHIDRA_HOME:-$(for d in "$HOME"/ghidra*/ghidra_*; do if [ -d "$d" ]; then echo "${d##*/} $d"; fi; done | sort -V | tail -1 | cut -d' ' -f2-)}"
echo "Ghidra: $GH"
[ -x "$GH/support/analyzeHeadless" ] || { echo "Ghidra not found: set GHIDRA_HOME (project.config or environment)"; exit 1; }
OUT="${GHIDRA_EXPORT_DIR:-ghidra}"; NAME="${PROJECT_NAME:-project}"
GNAME="$(printf %s "$NAME" | tr -c "A-Za-z0-9._-" "_")"      # the Ghidra project name: no spaces, "!" or other characters its files and paths dislike
SEEDS="${GHIDRA_SEEDS:-tools/ghidra/seeds.txt}"; LABELS="${GHIDRA_LABELS:-tools/ghidra/labels.txt}"; HOLES="${GHIDRA_HOLES:-tools/ghidra/holes.txt}"
# Paths may be relative to the project or absolute; from here on they are absolute.
for v in OUT SEEDS LABELS HOLES REFERENCE_PRG; do case "${!v}" in /*) ;; *) printf -v "$v" %s "$ROOT/${!v}";; esac; done
GPROJ="$OUT"; case "$OUT" in */.*) GPROJ="$HOME/ghidra_projects"; mkdir -p "$GPROJ"; echo "note: Ghidra refuses project folders under a dot directory: its project files go to $GPROJ";; esac
# The exporter (KickAssemblerExport.py) is found, in this order: GHIDRA_EXPORTER (project.config), the project's own tools/ghidra/exporter/ (fetched, pinned), ~/ghidra_scripts/ (a hand-installed copy),
# else it is fetched now from its repository at a pinned commit (fetch_exporter.py: needs the network once; nothing is installed into Ghidra's script directories, which differ per system).
EXP=""
for c in "${GHIDRA_EXPORTER:-}" "tools/ghidra/exporter/KickAssemblerExport.py" "$HOME/ghidra_scripts/KickAssemblerExport.py"; do
    if [ -n "$c" ] && [ -f "$c" ]; then EXP="$c"; break; fi
done
if [ -z "$EXP" ]; then
    echo "Kick Assembler exporter not found: fetching it (pinned) from https://github.com/Dave-Agent/ghidra-kickass-export"
    python3 -B "$HERE/fetch_exporter.py" --root "$ROOT" || { echo "no exporter: fetch failed (see above); set GHIDRA_EXPORTER to a copy of KickAssemblerExport.py"; exit 1; }
    EXP="tools/ghidra/exporter/KickAssemblerExport.py"
fi
case "$EXP" in /*) ;; *) EXP="$ROOT/$EXP";; esac
[ -f "$SEEDS" ] || { echo "no seeds file $SEEDS (scripts/ghidra/make_seeds.py writes one)"; exit 1; }
# Ghidra 12 and later has no Jython: its scripts run under PyGhidra (Python 3, needs JDK 25 for 12.2), started with `pyghidraRun -H`.
LAUNCH=("$GH/support/analyzeHeadless")
if [ ! -d "$GH/Ghidra/Features/Jython" ] && [ -x "$GH/support/pyghidraRun" ]; then LAUNCH=("$GH/support/pyghidraRun" -H); echo "note: this Ghidra has no Jython: running through PyGhidra (pyghidraRun -H)"; fi
mkdir -p "$OUT"
# remove only this project's previous Ghidra project files; ${VAR:?} stops the shell if a name is empty
rm -rf "${GPROJ:?}/${GNAME:?}.rep" "${GPROJ:?}/${GNAME:?}.gpr"
"${LAUNCH[@]}" "$GPROJ" "$GNAME" -import "$REFERENCE_PRG" \
    -processor "${GHIDRA_PROCESSOR:-6502:LE:16:default}" -loader BinaryLoader -loader-baseAddr "${LOAD_ADDRESS:-0x0800}" -overwrite \
    -scriptPath "$HERE" -postScript setup.py "$SEEDS" "$LABELS" "$HOLES" "$OUT" "$EXP" 2>&1 | grep -E "Export Complete|ERROR|Exception|Traceback|seeded|File|\.asm" || true
ls -la "$OUT"
