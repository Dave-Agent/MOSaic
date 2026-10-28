# Phase 2: the split procedure
Applies to: every project once phase 1 is complete (`SKILL.md`, Phases). Distilled from how IK+ and Monty did it; generic, no game or platform specifics. The aim is stated in `phase2_port.md`: a readable, relocatable source in which the game's logic is separated from the hardware it ran on, so a port becomes possible. The order matters: **steps 1-5 change no bytes (or only layout), so the phase 1 gate (`verify`) stays the gate until step 6; after step 6 the golden traces are the gate.**

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

## Step 4: the platform interface, one subsystem at a time
Input first (a clean cut), then time, sound, then drawing; see `phase2_port.md` for the layers and the contract style. Each change keeps the golden traces equivalent; a C64-ism left on purpose gets a marker: IK+ used `TODO(port)`, which is not yet in the skill's TODO tag set (`sound`, `user`, `code`, `phase2`, `name`, `block`); adopting it is an open decision for the user. **Layout-stable rule while the interface is introduced:** bytes change, addresses do not, because the routine tests, the golden state ranges and any noise window address the image; pad a routine that shrinks. Once the layout is free (end of step 6) this rule is retired. Make the routine tests the platform-neutral specification: a port runs the same tests against its own implementation.

## Step 5: make it relocatable
Run `scripts/reloc_scan.py` (indirect addressing, pointer tables, self-modifying code, code read as data, rts-dispatch tables) and resolve what is not removed in step 6; write the remaining hazards in `docs/relocation_hazards.md`. Run `scripts/layout_fuzz.py` (pad N bytes at chosen points, assemble, run the tests and traces on each variant): a failure is a hidden dependency. See `rules.md`, Relocatability, for the anchored-address rule.

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
