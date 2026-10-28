# Section-marker convention

Byte-neutral comment banners that delimit regions in the phase-1 monolith as
you identify them. They cost nothing in the assembled output, give you and
your tools coarse landmarks in the large source file, and pre-stage the
phase-2 file-split cut lines. When phase 2 arrives, splitting becomes "promote
these markers to files" rather than "work out where the seams are."

## Format

A section opens with a banner block. The machine-readable parts are the
`SECTION:` tag and the address range, both greppable.

```
;==============================================================================
; SECTION: sprite_engine
; RANGE:   $1000-$13FF
; STATUS:  understood            ; one of: unknown | partial | understood
; SUMMARY: Sprite multiplexer and per-frame VIC sprite pointer updates.
;==============================================================================
```

A section closes implicitly at the next `SECTION:` banner, so no end marker is
needed. Keep one section per contiguous region; if a region splits as
understanding sharpens, split the banner.

## Why these fields

- `SECTION:` a stable identifier, lowercase_snake. Becomes the phase-2 filename.
- `RANGE:` the C64 address span. Lets a later script find cut points and lets
  you cross-check against `symbols.asm` and verify-diff offsets.
- `STATUS:` tracks comprehension. `grep 'STATUS:  unknown'` lists what's left,
  which is your phase-1 progress bar and the no-unidentified-addresses checklist.
- `SUMMARY:` one line, human-facing.

## Greppability

```
grep -n 'SECTION:' "$SRC_MAIN"          # table of contents
grep -n 'STATUS:  unknown' "$SRC_MAIN"  # remaining work
grep -n 'RANGE:' "$SRC_MAIN"            # all region bounds
```

## Discipline

These accrete as a byproduct of understanding, not as a separate task. Add or
refine a banner whenever you finish reasoning about a region. Because they're
comments, they never threaten byte-identity, so there's no verify cost to
maintaining them.
