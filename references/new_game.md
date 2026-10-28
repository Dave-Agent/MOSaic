# Starting a new game: from disk image to a byte-identical build

**DRAFT, revised 2026-10-29 with the user's answers.** Written from what Monty, TOAS and IK+ actually did, the user's own five-step summary (`workflow.md`) and the user's answers to the draft's questions. Lines marked **(proposal)** are ideas the user floated that have not been proven on a project yet; **(gap)** marks something not yet known or not yet encountered.

The aim of this stage: a **reference image of the game only** (no crack, no loader, no intro), a source that assembles to it byte for byte, and a way to run it. Everything after that is the phase 1 loop (`SKILL.md`).

## 0. Principles
- **The reference is the game, not the media.** Crack code, loaders, depackers, trainers, intros, hi-score disk savers are not game; each is identified, proven removable and left out.
- **Derive, prove, document.** Every byte removed or restored has a stated reason and a test; the provenance is written down so anyone can repeat it from their own copy of the media.
- **Dynamic beats static here.** Run the real media in an emulator to the game's hand-off; do not guess a boot chain from a disassembly.
- **No game binaries in the repository** (`layout.md`): the derive script, a checksum and the README steps are what is committed.
- **Unattended.** Every step that can be scripted is, so it can be re-run and checked later.

## 1. Gather the media
1. Prefer a **non-cracked** release. If only a cracked one exists, find a **second release** (a different cracker): the bytes they do not share are the crack, which is how IK+ undid edits the first cracker had made (`docs/version_diff.md` there).
2. Put media in `original/` (not committed). Record file names, sizes and hashes in the README (how to supply them).
3. Note the platform facts that change timing and boot: PAL or NTSC, true-drive needs, fast loaders.

## 2. Find the hand-off
The hand-off is the moment the game code is in RAM, fully depacked, and the cracker's or loader's code is about to jump into it.
1. Boot the media in **VICE with true drive emulation** (x64sc). Pitfalls that cost time: never pass `-default` (the drive ROM comes from the user's `vicerc`); the binary monitor's bank 2 is ROM, not RAM, so use the **text monitor** (`bank ram`, `save "f" 0 0000 ffff`, strip the 2-byte header).
2. Work out the **boot chain** by running it: BASIC `SYS`, depacker stages (RLE, cruncher, copy loops), intro, key waits, the final jump. Write it down as you find it (template: IK+ `docs/boot_and_crack_analysis.md`: boot chain, the game, crack code in the game image, what the game needs at entry, unanswered).
3. Set a **breakpoint at game execution start** and check that decompression has finished (code present where the jump goes; no data still crunched). **(proposal, from the user)** Check it with an analysis: **trace over a range of bytes that matches a known game-running state**: pick a RAM range whose contents are known for a running game (from a second release, an earlier dump of the running game, or code you have already identified) and confirm the dump matches it at that moment. Not yet proven on a project; the first project that uses it should record how well it works.
4. **Export RAM** at that point as a 64 KB image (`dumps/`, not committed), unattended where possible (a script that patches the key waits so a headless run reaches the hand-off: `vice_handoff.py` in IK+). VICE is the tool used so far; the user is open to discussing alternatives. When the media is awkward, a small purpose-built emulator that records coverage can run the game's own unpacker headless and be **self-tested** against the dump (TOAS `tools/trace/c64trace.c`: the self-test unpacks the game and compares byte for byte).
5. **Games that load more code after the hand-off** (overlays, levels): none met yet. The objective does not change: every byte of game code and data is identified, and a reference is derived and proven for it. How a second or later image is captured and referenced is decided when the first such game is met, and recorded then. **(gap)**

## 3. Derive the clean reference
1. Keep the game's address range only (IK+: `$0800-$FEFF`, no load-address header).
2. **Remove crack code** range by range. For each range: say what it is, test the removal **alone and together, unattended** (break at the real hand-off, zero, let the game run, judge by screenshot). Restore any original bytes the crack overwrote (IK+: a hi-score hook restored to the original instructions; sample data restored from the other release).
3. **Beware the test harness itself**: a breakpoint placed inside the region you zero destroys the jump it was about to execute; single-step the jump first (an IK+ round of tests was invalid for this reason).
4. Archive each intermediate image; record **SHA-256 of every stage** in the README/`reference.sha256`; list what is left that is not game data but cannot be removed (IK+ keeps the start values for pages 1 and 2 the launcher uses).
5. Write `reference/README.md`: provenance, each step, the checksums, what may still be crack that nothing revealed.
6. A derive script (`make_reference.py` or equivalent) reproduces the image from the media + dump, so the repository needs only the script and the hash.
7. **Protection patterns met so far** (look for them): code used as an XOR key by an unscrambler; self-erasing code; swapped pages (`init` swaps two pages, the image holds them pre-swap: emit both as `.pseudopc` blocks at their run addresses); check bytes; REM-line stubs at the start of BASIC; a key-wait loop; the entry stack pointer patched into the game's own code (so the entry SP is part of the contract).

## 4. Recreate the machine state the game expects
Hand-written, **not game**, kept in `launcher/`. Establish what the game needs at entry and nothing else: stack pointer, zero page contents (an uninitialised index can run an IRQ off a table into data), page 1/2 start values, KERNAL vectors, work RAM cleared, the raster line it is entered on, what it does with `$01`. Test the launcher by booting it unattended and judging the first screens.

## 5. Ghidra
1. Import the reference at its load address as a raw binary (6502).
2. **Seed the entry points from the vectors** (decided with the user): look for the **NMI** vector and the **other vectors**: the hardware vectors at `$FFFA` (NMI), `$FFFC` (RESET), `$FFFE` (IRQ/BRK) and the RAM vectors the game installs (`$0314`-`$0319`, `$0318` NMI and the rest of the KERNAL vector table, and any game-installed raster/IRQ chain such as a vector rewritten each stage), then feed every target to Ghidra as an entry point. Add jump-table entries the game uses. If you have a tracer, its executed entry points and code/data ranges can be fed in as well (TOAS: `framework/ghidra/apply_entry_points.py` from a CSV; IK+: `tools/ghidra/IKPlusSetup.py`, `make_seeds.py`).
3. Export to Kick Assembler with the user's plugin (https://github.com/Dave-Agent/ghidra-kickass-export): the monolith plus `symbols.asm`, with the exporter's `[ADDR:bytes MNEMONIC]` end-of-line comments and XREF comments, which stay (they trace back to the original; `rules.md`).
4. Never edit Ghidra and the source in both directions at once (`just sync-state`, `synced`).

## 6. The first byte-identical build
1. Copy the skill's `framework/` and `libs/`; write `project.config` (paths and names only) and the thin `justfile` (`just.md`); set up the layout (`layout.md`).
2. Assemble the exported source; `just verify` against the reference. **(gap)** The usual first diffs and how they are cleared are not known yet (the user is unsure); candidates seen in IK+ are a load address, data exported as code, bytes under the ROM and a `.pseudopc` swap. Record the real list after the next game.
3. Commit as the baseline. From here the loop in `SKILL.md` applies: byte-identical is returned to at every commit.
4. **Test the build and the game start** (decided with the user): assemble, `verify`, then start the game and check unattended that it boots to a recognisable screen (`just smoke`, a screenshot judge).

## 7. What the project should have when this stage is done
- `README.md`: the game and release, what to supply, the checksum, the one command that derives `reference/` and verifies it.
- `docs/boot_and_crack_analysis.md` (or equivalent) and `reference/README.md` (provenance).
- `reference.sha256`, the derive script, `launcher/`, `project.config`, `justfile`, `framework/`, `libs/`.
- A passing `just verify` and `just smoke`, and a first `p1_complete.py` run to see how far there is to go.

## Answers so far and what is still open
- Breakpoint and decompression check: analysis by tracing a range of bytes that matches a known game-running state (proposal, unproven).
- Tool for the dump: VICE so far; open to discuss alternatives (a tracer, the cracker's tools).
- Ghidra seeds: the NMI and other vectors (stage 5).
- First diffs when the export is first assembled: unknown yet; to be written from the next game.
- Games that load more code after the hand-off: none yet; the objective is unchanged.
- Order of stages: the user's order is the same as the draft's.
- Stage 7 (done) includes testing the build and the game start.
