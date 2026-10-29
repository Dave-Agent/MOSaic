# Slice checklist (one page: the rules a slice most often breaks)

Read before starting a slice, and run `just slice-check` (`scripts/slice.py check`) before calling it done. The full rules are in `rules.md`, `naming.md`, `phase1_method.md`.

**Work**
- Work in a scratch copy (`just slice-start NAME`), commit there with a path-limited `git add`, never `git checkout/reset/restore/clean`. Merge with `just slice-merge NAME`.
- The build stays byte-identical at every commit (`just verify`).
- No guessing: describe what the code does; a name that claims a role needs the document (rung 1) AND an observation (rung 3, a controlled tracer run). Otherwise a descriptive name plus `TODO(name)`. Ask the owner only what a thing IS to a player, with a picture, after trying the code.

**Markers (every one has a headline sentence)**
- `TODO(user)` needs the owner; `TODO(name)` provisional name; `TODO(block)` other phase 1 blocker; `TODO(sound)`, `TODO(code)`, `TODO(port)` hardware dependency, `TODO(phase2)` change for phase 2.
- **A label nothing refers to** (dead code, a utility nothing calls, leftover data) gets `TODO(phase2): remove? unreferenced, never executed`. `unreferenced.py --write` puts it on; `slice-check` fails without it. Decode and comment it anyway; never delete it in phase 1.

**Data**
- One record per row for a table of fixed-size records (`refactor/records.py`); a list's end marker on its own row; a block that runs past its end marker is a label missing (`sentinel_scan.py`).
- Text is text (the project's text macro), never `.byte` rows.
- A data row keeps `// [addr]` only: no operand-name list, no ASCII dump (`comment_check.py --fix`).
- Pointers are labels (`.word label`, `#<label`); no raw `$ADDR` operands; no `label+n` in uses.

**Names**
- Routines PascalCase, data snake_case, constants UPPERCASE; zero page `zp_` in phase 1. Unique within a family (two records of one shape in two colours need a colour in the name).
- Local labels: scope the routine, anonymous labels only for trivial skips and loops (`just anon-check`).

**Comments**
- Wrap at 128 columns (`comment_check.py --fix`); a label line summary under 80 characters; detail in the block above.
- A comment says what the line does not. Keep every `[ADDR:bytes MNEMONIC]` trace comment.

**Report back**: the commits, the `slice check` output, `p1_complete` before/after, anything not settled (as a marker, not a guess).
