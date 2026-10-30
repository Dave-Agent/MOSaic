#!/usr/bin/env bash
# framework/scripts/verify.sh
# The gate. Assembles canonical source and checks the output against the reference.
# Green => no drift from byte-identity.
#
# Two ways to check, chosen automatically:
#   * Reference image present (REFERENCE_PRG exists): byte-for-byte compare. On failure
#     it reports the first diverging offset (as an image offset and a C64 address), which
#     against a monolith is the difference between a 5-minute fix and an afternoon.
#   * Reference image absent: compare the SHA-256 of the built image with the one recorded
#     for REFERENCE_PRG in REFERENCE_SHA256_FILE (sha256sum format: "<hash>  <path>").
#     This lets a clone verify without the original binary ever being in the repository.
#
# KickAssembler always emits a .prg with a 2-byte load-address header. If the
# reference is a raw memory dump (no header), set REFERENCE_IS_RAW="true" in
# project.config; the header is then stripped from the built side so the
# comparison is memory-image to memory-image. The hash is of that same headerless image.
#
# Usage: verify.sh
# Exit 0 = identical, 1 = drift, 2 = cannot verify (no reference and no recorded hash).

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
cd "$PROJECT_ROOT"

# shellcheck disable=SC1091
source ./project.config

# Phase 2 (C64_PHASE=2, set by `just verify 2`): the same gate on the split source: PHASE2_MAIN assembled into $BUILD_DIR/p2/game.prg.
if [ "${C64_PHASE:-1}" = "2" ]; then
    [ -n "${PHASE2_MAIN:-}" ] && [ -f "$PHASE2_MAIN" ] || { echo "!! C64_PHASE=2 but PHASE2_MAIN is not set or not a file" >&2; exit 2; }
    SRC_MAIN="$PHASE2_MAIN"; BUILD_DIR="$BUILD_DIR/p2"; OUTPUT_PRG="$BUILD_DIR/game.prg"
fi

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
    else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

# Python scripts must not leave __pycache__ in the skill directory, also when this script is run without just.
export PYTHONDONTWRITEBYTECODE=1

# Optional pre-verify hook. Set PRE_VERIFY_HOOK in project.config to run any
# project-specific command before assembly (e.g. comment alignment).
if [ -n "${PRE_VERIFY_HOOK:-}" ]; then
    eval "$PRE_VERIFY_HOOK"
fi

# The recorded hash for the reference, if any.
REFERENCE_SHA256_FILE="${REFERENCE_SHA256_FILE:-${REF_SHA_FILE:-}}"     # make_reference.py writes REF_SHA_FILE: one name is enough
EXPECTED_SHA=""
if [ -n "${REFERENCE_SHA256_FILE:-}" ] && [ -f "$REFERENCE_SHA256_FILE" ]; then
    EXPECTED_SHA=$(awk -v f="$REFERENCE_PRG" -v b="${REFERENCE_PRG##*/}" '$2 == f || $2 == b { print $1 }' "$REFERENCE_SHA256_FILE")
fi

if [ ! -f "$REFERENCE_PRG" ] && [ -z "$EXPECTED_SHA" ]; then
    echo "!! cannot verify: no reference image at $REFERENCE_PRG" >&2
    echo "   and no SHA-256 recorded for it${REFERENCE_SHA256_FILE:+ in $REFERENCE_SHA256_FILE}." >&2
    echo "   (supply the reference image, or record its hash; see README.md)" >&2
    exit 2
fi

# Assemble first.
PROJECT_ROOT="$PROJECT_ROOT" bash framework/scripts/build.sh --quiet

if [ ! -f "$OUTPUT_PRG" ]; then
    echo "!! no built PRG at $OUTPUT_PRG" >&2
    exit 2
fi

# Strip the load-address header from the built side when the reference is a raw dump.
# The header is not part of the image or its hash, so check it separately: the same bytes
# assembled at the wrong address would otherwise pass.
if [ "${REFERENCE_IS_RAW:-false}" = "true" ]; then
    BUILT_LOAD=$(( $(od -An -tu1 -N1 "$OUTPUT_PRG") + 256 * $(od -An -tu1 -j1 -N1 "$OUTPUT_PRG") ))
    if [ "$BUILT_LOAD" -ne $(( LOAD_ADDRESS )) ]; then
        printf "FAIL: built PRG loads at \$%04X, expected \$%04X (LOAD_ADDRESS in project.config)\n" \
            "$BUILT_LOAD" "$(( LOAD_ADDRESS ))"
        exit 1
    fi
    BUILT_IMAGE=$(mktemp)
    tail -c +3 "$OUTPUT_PRG" > "$BUILT_IMAGE"
    trap 'rm -f "$BUILT_IMAGE"' EXIT
else
    BUILT_IMAGE="$OUTPUT_PRG"
fi
BUILT_SHA=$(sha256_of "$BUILT_IMAGE")

# Where the compared bytes sit in C64 memory. A raw reference starts at LOAD_ADDRESS. A PRG reference (REFERENCE_IS_RAW="false") carries its load address in its first two
# bytes (little-endian) and its image starts at the third byte, which lands there: the compare is of whole files, header included, and the address of byte N is base + N - 2.
IMG_SKIP=0; IMG_BASE=$(( ${LOAD_ADDRESS:-0} ))
if [ "${REFERENCE_IS_RAW:-false}" != "true" ] && [ -f "$REFERENCE_PRG" ]; then
    IMG_SKIP=2; IMG_BASE=$(( $(od -An -tu1 -N1 "$REFERENCE_PRG") + 256 * $(od -An -tu1 -j1 -N1 "$REFERENCE_PRG") ))
    if [ -n "${LOAD_ADDRESS:-}" ] && [ $(( LOAD_ADDRESS )) -ne "$IMG_BASE" ]; then
        printf 'FAIL: LOAD_ADDRESS %s in project.config disagrees with the PRG header of %s ($%04X)\n' "$LOAD_ADDRESS" "$REFERENCE_PRG" "$IMG_BASE"; exit 1
    fi
fi

# ---- no reference image: hash gate ------------------------------------------------
if [ ! -f "$REFERENCE_PRG" ]; then
    if [ "$BUILT_SHA" = "$EXPECTED_SHA" ]; then
        echo "PASS: built image matches the SHA-256 recorded for $REFERENCE_PRG"
        echo "      (${BUILT_SHA:0:16}...; reference image not present, so no byte-level diff is available)"
        exit 0
    fi
    echo "FAIL: built image does not match the SHA-256 recorded for $REFERENCE_PRG"
    echo "      expected $EXPECTED_SHA"
    echo "      built    $BUILT_SHA"
    echo "      Supply the reference image at $REFERENCE_PRG to find the first differing address."
    exit 1
fi

# ---- reference image present: byte-level compare ----------------------------------
REF_SIZE=$(wc -c < "$REFERENCE_PRG" | tr -d " ")      # not stat: its flags differ between GNU and BSD (macOS)
OUT_SIZE=$(wc -c < "$BUILT_IMAGE" | tr -d " ")

if [ "$REF_SIZE" -ne "$OUT_SIZE" ]; then
    echo "FAIL: size mismatch. reference=$REF_SIZE bytes, built image=$OUT_SIZE bytes"
    echo "      (a size delta usually means a missing/extra data block, not a code edit)"
    exit 1
fi

# Phase 2, byte-changing steps with APPROVED changes (PHASE2_ALLOWED_DIFF: a file of `LO-HI` C64 address ranges in hex, one per line, `#` comments): the built image may differ from the reference
# only inside those ranges (a removed block left as a hole, an operand rewritten on purpose); every other byte must be identical. A byte outside them fails the gate and names the first one.
if [ "${C64_PHASE:-1}" = "2" ] && [ -n "${PHASE2_ALLOWED_DIFF:-}" ] && [ -f "$PHASE2_ALLOWED_DIFF" ] && ! cmp -s "$REFERENCE_PRG" "$BUILT_IMAGE"; then
    python3 - "$REFERENCE_PRG" "$BUILT_IMAGE" "$PHASE2_ALLOWED_DIFF" "$IMG_BASE" "$IMG_SKIP" <<'PY'
import sys
ref, new, rf, load, skip = open(sys.argv[1], 'rb').read(), open(sys.argv[2], 'rb').read(), sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
rng = []
for l in open(rf):
    l = l.split('#')[0].strip()
    if l: lo, hi = l.replace('$', '').split('-'); rng.append((int(lo, 16), int(hi, 16)))
bad = [load + i - skip for i in range(len(ref)) if ref[i] != new[i] and (i < skip or not any(lo <= load + i - skip <= hi for lo, hi in rng))]      # a differing header byte is never allowed
changed = sum(1 for i in range(len(ref)) if ref[i] != new[i])
if bad: print('FAIL: %d byte(s) differ outside the allowed ranges (%s); first at $%04X: reference %02X, built %02X' % (len(bad), rf, bad[0], ref[bad[0] - load + skip], new[bad[0] - load + skip])); sys.exit(1)
print('PASS: identical to the reference except %d byte(s), all inside the allowed ranges (%d ranges in %s)' % (changed, len(rng), rf))
PY
    exit $?
fi

if cmp -s "$REFERENCE_PRG" "$BUILT_IMAGE"; then
    if [ -n "$EXPECTED_SHA" ] && [ "$EXPECTED_SHA" != "$BUILT_SHA" ]; then
        echo "FAIL: built image is identical to $REFERENCE_PRG, but the SHA-256 recorded in"
        echo "      $REFERENCE_SHA256_FILE is different: the hash file or the reference image is stale."
        exit 1
    fi
    echo "PASS: built image is byte-identical to $REFERENCE_PRG"
    exit 0
fi

# First divergence. cmp reports "byte N" or "char N" (1-indexed) into the compared
# image. The headerless image starts exactly at the load address, so the C64
# address is LOAD_ADDRESS + image offset (no header fudge).
FIRST=$( (cmp "$REFERENCE_PRG" "$BUILT_IMAGE" 2>&1 || true) | awk '{ for (i = 1; i <= NF; i++) if ($i == "differ:") { n = $(i + 2); sub(/,/, "", n); print n } }')     # "differ: byte N" (GNU 3.4+) or "char N" (BSD, older GNU); cmp exits 1 on a difference, which set -e would take as a failure
IMAGE_OFFSET=$(( FIRST - 1 ))
C64_ADDR=$(( IMG_BASE + IMAGE_OFFSET - IMG_SKIP ))

ref_byte=$(od -An -tx1 -j "$IMAGE_OFFSET" -N1 "$REFERENCE_PRG" | tr -d ' ')
out_byte=$(od -An -tx1 -j "$IMAGE_OFFSET" -N1 "$BUILT_IMAGE" | tr -d ' ')

if [ "$IMAGE_OFFSET" -lt "$IMG_SKIP" ]; then echo "FAIL: the load address (the first two bytes of the PRG) differs"; else printf "FAIL: first divergence at image offset 0x%X (C64 \$%04X)\n" "$IMAGE_OFFSET" "$C64_ADDR"; fi
printf "      reference byte: 0x%s   built byte: 0x%s\n" "$ref_byte" "$out_byte"
echo "      grep symbols.asm for the label at or below \$$(printf '%04X' "$C64_ADDR") to localise."
exit 1
