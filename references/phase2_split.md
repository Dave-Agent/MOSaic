# Phase 2: the split procedure
Applies to: every project once phase 1 is complete (`SKILL.md`, Phases). Distilled from how real projects did it; generic, no game or platform specifics. The aim is stated in `phase2_port.md`: a readable, relocatable source in which the game's logic is separated from the hardware it ran on, so a port becomes possible. The order matters: **steps 1-5 change no bytes (or only layout), so the phase 1 gate (`verify`) stays the gate until step 6; after step 6 the golden traces are the gate.**

## Decisions that frame it
- **Both versions stay in the repository**: `phase1/src` is the byte-identical monolith for reading the original byte per byte (tag its last state, e.g. `p1-byte-identical`), `phase2/src` is the refactored source. Byte-identity is given up deliberately, at step 6 only.
- **No `.filenamespace` per file.** Subsystems are grouped by explicit `.namespace` blocks; a per-file namespace would force a qualifier on every cross-file reference to a top-level routine, for no gain in readability.
- **Write the plan down first** (`docs/phase2_plan.md`): goal, portability requirements, the order below, and "where things stand". Update it as steps finish.

## Step 1: the safety net (no source change)
Before anything moves, pin the behaviour. Build the tests, golden traces and gates (`testing.md`): a routine test for every extractable routine (a model in plain Python written from the source), golden traces of the game's observable state per frame for seeded scenarios (attract mode, each round type, the score screens, two players), coverage to see what the scenarios never reach, and one command that runs everything (`check`). Keep `verify`, `raw_refs`, the relocation scan and the smoke test green throughout. Routines that call others you cannot isolate (the move engine, the AI) may stay without a routine model; say so.

## Step 2: the hardware dependency catalogue (documentation only)
`scripts/platform_deps.py` lists, per routine, every reference to the hardware libs and to display memory. Write `docs/platform_layer.md` from it, and classify each entry: **platform layer** (stays hardware-specific), **game logic that calls the platform** (needs an interface), or **logic that accidentally depends on the platform** (to be fixed). Propose the interface (`Gfx`, `Sound`, `Input`, `Time` by domain).

## Step 3: split into files, still byte-identical
`scripts/split_section.py` moves one `SECTION` (or several consecutive ones that a namespace spans) from the main file into `DIR/name.asm` and leaves an `#import`; run the gate after **every** file moved. Group by layer: `game/` (logic), `platform/` (the hardware's way of doing things), `data/` (graphics, tables, text; files stay in address order, so a few import each other until a later compaction). Label files (`symbols.asm`, `zero_page.asm`, ...) come with the split. The main file shrinks to the imports and what must stay at fixed addresses. **Keep the jump table** (the fixed-address call slots) until step 6: removing it changes bytes and timing.

Several sections at once: `scripts/split_all.py PLAN` takes one `DIR<TAB>SECTIONS<TAB>BASE` line per file, runs the gate (`just verify 2`) after EVERY move and commits each, so a failure names the section. A banner that mixes layers (code and data, platform and logic) is not cut apart here: name its file `..._mixed` and cut it in step 4 where the interface needs it. Assertions and anchored data travel with their section, so the main file ends up as the header, the label-file and library imports, the start address and one `#import` per file in address order. `split_section.py` cuts strictly banner to banner (everything between two banners goes with the section), so every label scope, assert and data run must lie inside one banner; it does not rewrite relative imports that point into sibling files.

Cuts that phase 1's banners do not offer (a routine or table that starts mid-section, the usual case for the interface work): `scripts/cut_section.py SECTION --at LABEL NEWNAME DIR/BASE` cuts the section's file at the label (its leading comment block goes with it), writes fresh banners with computed `RANGE:` lines so the banners still tile the image, and imports the new file right after the old one. Do the cut, run the gate, then rename.

## Step 3b: the label files to their final form (still byte-identical)
After the split and before the interface work, bring the label files to the form of `rules.md`, "Phase 2 label files". Each step is comments and names only; `just verify 2` and the saved SHA-256 of the build must not change.
1. `python3 scripts/refactor/drop_xrefs.py --write`: the XREF lists go (phase 1 stays the trace).
2. `python3 scripts/refactor/zp_virtual.py --write`: `zero_page.asm` becomes the namespace and virtual segment, every use becomes `zp.name`, `tools/name_map.tsv` keeps the old spellings findable for the tests and golden scenarios. For `variables.asm` (and other RAM label files): `--file variables.asm --region LO-HI --namespace ram --segment Variables` converts the labels of one region into a file of its own; what is not a game variable (screen and colour RAM cells, KERNAL entry points) stays as `.label`, ideally in a file of the machine's memory map.
3. `python3 scripts/refactor/tidy_comments.py FILE --write` for each label file, and `tidy_comments.py ALL --prose --write` for the block comments of the code files: the mechanical part of the comments (read the diff: a clause that is not narrative but mentions a doc or a frame number is lost with it). Then shorten by hand what is still too long for the end of its line; the evidence behind a name goes to `docs/evidence.md` (`scripts/evidence.py`), not the comment.
4. Set `PHASE2_LABEL_STYLE="standard"` in `project.config` when `just comment-check` reports no hint left.
Grouping the variables by subsystem is the one step that moves addresses (the code addresses them by name, so only operands change): do it last, with the relocation scan and a gate that accepts only changed zero-page operands, plus the tests, the golden traces and the smoke test; the pre-regroup build becomes the new baseline for the byte-identity check.

## Step 4: the platform interface, one subsystem at a time
Input first (a clean cut), then time, sound, then drawing; see `phase2_port.md` for the layers and the contract style. Each change keeps the golden traces equivalent; a C64-ism left on purpose gets a marker (a project used `TODO(port)`, which is not yet in the skill's TODO tag set (`sound`, `user`, `code`, `phase2`, `name`, `block`); adopting it is an open decision for the user). **Layout-stable rule while the interface is introduced:** bytes change, addresses do not, because the routine tests, the golden state ranges and any noise window address the image; pad a routine that shrinks. Once the layout is free (end of step 6) this rule is retired. Make the routine tests the platform-neutral specification: a port runs the same tests against its own implementation.

## Step 5: make it relocatable
Run `scripts/cpu/6502/reloc_scan.py` (indirect addressing, pointer tables, self-modifying code, code read as data, rts-dispatch tables) and resolve what is not removed in step 6; write the remaining hazards in `docs/relocation_hazards.md`. Run `scripts/layout_fuzz.py` (pad N bytes at chosen points, assemble, run the tests and traces on each variant): a failure is a hidden dependency. See `rules.md`, Relocatability, for the anchored-address rule.

## Step 6: the byte-changing removals (regenerate `reference/` for this step)
- **Protection**: unscramblers and scrambled headers, check bytes and their tamper traps, return-address tricks; each has a `TODO(phase2)` marker from phase 1.
- **Page swaps**: store each page at its run address.
- **Drive-code remnants and dead blocks.**
- **A noise source that is a window into code** gets a dedicated table.
- **The jump table**: calls become direct (`@Name` for root-scope names inside namespaces); re-record the golden traces after checking the differences are only timing.
- **Debug aids as tooling, not source**: monitor labels with the full namespace paths and optional breakpoints are generated from the symbol file (`.break` / `.watch` in the source would stop the emulator at every launch).
- **Timing-tolerant traces**: any change of bytes changes cycle timing, and a game that uses the raster counter as noise or polls the keyboard at a phase of the frame cannot keep exact traces. Record traces with the raster-as-noise replaced by a private generator and accept a late drift: a break in the first seconds fails, a subtle late one may not be caught (state that limit in the plan).

## Measurements to take along the way
The game logic's CPU cost per frame (everything except drawing and sound) for each scenario, the number of platform-layer calls per frame and the size of the data they move, and the needs of any sample or timer-driven sound. These are the numbers a port budgets with.

## Done when
`just check` passes; the source is split and namespaced; every remaining hardware dependency is behind the interface or marked `TODO(port)`; the layout is free with only hardware-fixed data anchored; `docs/porting.md` and `docs/platform_layer.md` exist and are current; the plan says where things stand.

## Step 6 with a masked gate: remove without moving
Removing a dead block and letting everything after it move down changes the layout and the timing of live code (a taken branch that crossed a page may stop crossing it), and every address anchored to hardware has to be re-anchored. The cheaper and safer form: remove the block and leave a HOLE: an absolute `.pc = <next live address>` after the removed block, so every live byte keeps its address. The image then differs from the reference only inside the removed ranges, timing is untouched, the exact golden traces still apply, and the gate can prove it: list the removed (and deliberately rewritten) address ranges in a file (`PHASE2_ALLOWED_DIFF` in project.config, one `LO-HI` hex range per line, `#` comments) and `just verify 2` passes only when every differing byte lies inside them; a changed byte anywhere else fails and is named. Compacting the layout to use the freed space is a separate, optional step (relocation sweep and the timing hazards of testing.md apply).

**Removing an instruction inside live code** (a write or a test in the middle of a routine, not a whole block): replace it with `NOP`s of the same length, so nothing after it moves. The NOPs take the cycles of the removed instruction out, so the timing of that routine changes and the exact golden traces no longer apply: use the timing-tolerant set (`just golden 2`). List the NOPped bytes in the allowed-ranges file like a hole.

**Record the removals in `docs/phase2_removals.md`**: every removed block or NOPped instruction with its address range, size and the owner's decision. `just status` recognises step 5 by this file.
