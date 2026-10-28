#!/usr/bin/env bash
# Save a baseline PRG before a rename/restructure and compare after: a pure rename must leave the build byte-identical.
#   build_compare.sh save FILE [KEEP]       copy FILE to KEEP (default FILE.baseline)
#   build_compare.sh compare FILE [KEEP]    cmp FILE against the baseline; exit 1 if different
set -euo pipefail
mode=${1:?save|compare}; f=${2:?built file}; keep=${3:-$f.baseline}
case $mode in
  save) cp "$f" "$keep"; echo "baseline saved: $keep" ;;
  compare) if cmp "$f" "$keep"; then echo "IDENTICAL to baseline"; else echo "DIFFERENT from baseline"; exit 1; fi ;;
  *) echo "usage: $0 save|compare FILE [KEEP]"; exit 2 ;;
esac
