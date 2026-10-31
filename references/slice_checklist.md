# Slice checklist (one page: the rules a slice most often breaks)

Read before starting a slice, and run `just slice-check` (`scripts/slice.py check`) before calling it done. The full rules are in `rules.md`, `naming.md`, `phase1_method.md`.

**Work**
- Work in a scratch copy (`just slice-start NAME`), commit there with a path-limited `git add`, never `git checkout/reset/restore/clean`. Merge with `just slice-merge NAME`.
- The build stays byte-identical at every commit (`just verify`).
- A slice is **reviewed by a second agent before it merges** (`references/challenger.md`; `just review-brief NAME`): it answers every review-only rule (`rules_table.py --unenforced`) and tries to refute the names the slice introduces. Any new commit needs a new review. Write the names so they survive that: a name that claims a role carries its document and its observation.
- Evidence goes to `docs/evidence.md` (`scripts/evidence.py NAME TEXT`), not into the comment: the comment states the conclusion at the end of the line in about 80 characters (`rules.md`, "Phase 2 label files").
- No guessing: describe what the code does; a name that claims a role needs the document (rung 1) AND an observation (rung 3, a controlled tracer run). Otherwise a descriptive name plus `TODO(name)`. Ask the owner only what a thing IS to a player, with a picture, after trying the code.

**Slices run in parallel**: do not run `just align` / `align_comments.py` in a slice (it rewrites the comment columns of the whole file and every other slice then conflicts on merge); the lead runs it once, between merges. Edit only your range.
- A whole-source `slice check` cannot pass while other slices still carry `TODO(name)` markers: judge a slice by `--range LO-HI --allow-marked`; the whole-source check is for the last slice.
- Tracer flags cannot tell ROM code from RAM data at the same address: with the ROM banked in, check 7 of `p1_complete` can list ROM routines as "data rows that ran as code": pass `--exec-ignore LO-HI`.

**Markers (every one has a headline sentence)**
- `TODO(user)` needs the owner; `TODO(name)` provisional name; `TODO(block)` other phase 1 blocker; `TODO(sound)`, `TODO(code)`, `TODO(port)` hardware dependency, `TODO(phase2)` change for phase 2.
- **A label nothing refers to** (dead code, a utility nothing calls, leftover data) gets `TODO(phase2): remove? unreferenced, never executed`. `unreferenced.py --write` puts it on; `slice-check` fails without it. Decode and comment it anyway; never delete it in phase 1.

**Data**
- One record per row for a table of fixed-size records (`refactor/records.py`); a list's end marker on its own row; a block that runs past its end marker is a label missing (`sentinel_scan.py`).
- Text is text (the project's text macro), never `.byte` rows.
- A data row keeps `// [addr]` only: no operand-name list, no ASCII dump (`comment_check.py --fix`).
- Data reached by index, not by name (sprite or character pictures, tile tables): `unreferenced.py` sees no reference. Give it one that states the index: a `.assert` or a constant that names the label and its index (`.assert "frame block", <expression using the label>, $NN`), so the label is referenced and the number is checked. Mark `TODO(phase2): remove?` only where the code and the runs show it is unused.
- Ghidra puts labels of ROM routines into RAM data and disassembles pixel or table bytes as instructions there (fake `ror`, `brk`, raw operands under the ROM): the ROM routine labels belong in `variables.asm` (as `.label ROM_x = $ADDR`), and the fake instructions go back to data rows (`refactor/code_to_bytes.py`).
- Pointers are labels (`.word label`, `#<label`); no raw `$ADDR` operands; no `label+n` in uses.

**Names**
- Routines PascalCase, data snake_case, constants UPPERCASE; zero page `zp_` in phase 1. Unique within a family (two records of one shape in two colours need a colour in the name).
- Local labels: scope the routine, anonymous labels only for trivial skips and loops (`just anon-check`).

**Comments**
- Wrap at 128 columns (`comment_check.py --fix`); a label line summary under 80 characters; detail in the block above.
- A comment says what the line does not. Keep every `[ADDR:bytes MNEMONIC]` trace comment.

**Report back**: the commits, the `slice check` output, `p1_complete` before/after, anything not settled (as a marker, not a guess).
- Progress notes: `slice.py note NAME "..."` at every milestone and before any run that takes more than a couple of minutes; the starter reads `slice.py status NAME` (commits, uncommitted files, the last notes, time since anything moved). A slice with no notes and no activity is a stuck slice.
