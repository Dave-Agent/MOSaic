# Hand-off and reference tools (stages 2-4 of `new_game.md`)

Generic scripts, all in `scripts/`, all taking `--root` (the project root, default the current directory), reading `project.config` for defaults and printing what they did. Placeholders below: `MEDIA` (disk or tape image), `HANDOFF` (the address of the jump into the game), `LO-HI` (the game's address range).

| Script | Stage | What it does |
|---|---|---|
| `vice/vice_handoff.py` | 2 | Boots MEDIA in VICE (headless-capable, warp, true drive), patches key waits, runs to HANDOFF, dumps the 64 KB RAM. Also tests a removal (`--after`) and takes a screenshot. |
| `vice/vice_monitor.py` | 2-4 | The text-monitor client (`Monitor` class and a one-shot CLI). The other VICE scripts use it. |
| `vice/vice_symbols.py` | 4+ | Kick symbol file to VICE monitor labels with the full namespace path, plus breakpoints and watches. |
| `vice/judge_screenshot.py` | 4, 6 | Scores a screenshot against a reference picture (whole or a crop). |
| `reference/make_reference.py` | 3 | Dump to reference image: keep LO-HI, zero listed ranges, apply byte patches, copy ranges from a second release; prints the SHA-256 of every input and of the result. |
| `reference/dump_diff.py` | 1, 3 | Diffs two dumps (two releases, or two moments) into regions with the nearest label. |

## project.config keys these scripts read
`VICE_BIN` (x64sc), `VICE_MONITOR_PORT` (6510), `HANDOFF_MEDIA`, `HANDOFF_BREAK`, `HANDOFF_DUMP`, `HANDOFF_TIMEOUT`, `REF_DUMP`, `REF_SPEC`, `REF_KEEP`, `REF_OUT`, `REF_SHA_FILE`, `DIFF_RANGE`, `SYMBOL_FILE`, `JUDGE_REF`, `JUDGE_CROP`, `JUDGE_TOLERANCE`, `JUDGE_MIN_SCORE`. Every one is also an option; the header of each script says which. Options win over the file.

## Stage 2: reach the hand-off unattended
1. Work out the boot chain interactively first (breakpoints at each stage: BASIC `SYS`, depacker, intro, final jump). The tool does not find the hand-off; it repeats a path you already know.
2. Write the path as `--step` options, in order. Each `--step 'ADDR=CMD;CMD'` runs to ADDR, deletes the breakpoint and sends monitor commands: that is how a key wait is made to fall through (a patched `lda`/`bne`, two NOPs). Then `--handoff HANDOFF` is the final breakpoint. A prompt that wants a key (a hi-score name, "press space") is answered with `--feed '> 0277 4e;> c6 01'` (pokes the keyboard buffer and its length, re-sent at every poll).
3. Run:
   `scripts/vice/vice_handoff.py --media originals/MEDIA --handoff HANDOFF --out dumps/NAME_handoff.bin --step 'ADDR=> ADDR EA EA' --feed '...' --io`
   The dump is 65536 bytes of true RAM, taken one instruction after the break (see gotchas). `--io` adds `NAME.io.txt` (VIC, SID, CIA, colour RAM, CPU registers): the input to stage 4.
4. A run takes about a minute in warp. Commit the command line (a `just` recipe or the README), not the dump.

### What varies between runs
Two unattended runs of the same media gave dumps that differ in a handful of bytes outside the game: the zero-page RAM under the CPU port (`$00/$01`), the jiffy clock low byte, and a few stack residue bytes. They are timing artefacts of a headless run, not part of the game. Judge two dumps with `dump_diff.py`; only differences inside LO-HI matter.

## Stage 3: derive the reference
1. Write the spec file (`reference/derive.spec` or similar), one line per operation, every line with a reason after `#`:
   ```
   bytes ADDR HH HH HH   # original instructions the crack replaced
   zero  LO HI           # crack code / loader / menu
   ```
2. `scripts/reference/make_reference.py --in dumps/NAME_handoff.bin --keep LO-HI --spec reference/stage1.spec --out reference/archive/NAME_stage1.bin --write`. It prints the number of bytes each line changes (0 means the spec and the dump already agree: check for a typo) and the SHA-256 of input and output. Archive every stage and record the hashes in `reference/README.md`.
3. **Second release step.** Dump the second release at the same moment (same hand-off state), then a second spec with `copy LO HI NAME` lines (the second release's bytes where the first cracker edited the game) and `zero` lines; run it with `--in <stage 1 image> --in-base LO --source NAME=dumps/other.bin --expect-sha256 HASH`. `dump_diff.py A B` lists where two releases differ, nearest label included (`--symbols`), which is how the `copy` ranges are found. What both releases share can still be crack code: the tool cannot see that.
4. Each removal is proven before it goes into the spec: `vice_handoff.py ... --after '> ADDR 91 52 60;f LO HI 00' --run-seconds 60 --screenshot out.png --expect LO-HI:BYTES`, then `judge_screenshot.py`. Test each alone and all together.
5. `--expect-sha256` makes a re-run fail loudly when anything differs from the recorded hash; `--sha-file` (with `--write`) writes the `reference.sha256` line.

## Stage 4: judge the launcher and the first builds
`judge_screenshot.py --ref REF.png [--crop X0,Y0,X1,Y1] SHOT.png` prints a score and PASS/FAIL (exit code 1 on fail). Take SHOT the way the project's smoke recipe does: `x64sc -warp +confirmonexit -drive8truedrive -drive8type 1541 -jamaction 5 -autostart PRG -limitcycles N -exitscreenshot SHOT.png`. Take REF the same way, once, from a run you checked by eye. Choose a crop over something static on the target screen (a title, a status bar), not an animated area. A different image size scores -1 (FAIL).

`vice_symbols.py SYMFILE OUT.mon [--break NAME] [--watch NAME]` makes a monitor command file with `Namespace.Routine.local` labels (Kick's own `-vicesymbols` drops the namespace); start VICE with `-moncommands OUT.mon`.

## VICE gotchas (each one cost an afternoon)
- **Never pass `-default`.** The 1541 ROM only resolves through the user's `~/.config/vice/vicerc`; with `-default` the drive hangs at SEARCHING FOR *. The option is `-drive8truedrive`, not `-truedrive`.
- **Use the text monitor** (`-remotemonitor`), not the binary monitor: the binary monitor's bank 2 is ROM, so a RAM dump through it is wrong wherever the game runs under the ROMs. In the text monitor give `bank ram` before `save "f" 0 0000 ffff`.
- **Step the jump before editing.** After the breakpoint at the jump, execute it (`z`) before changing memory: a test that zeroes the range the jump sits in, with the breakpoint still on it, destroys the instruction about to run, and the whole round of tests is invalid. `vice_handoff.py` does the step by default (`--no-step` to disable).
- **Judge by screenshot, not by a PC sample or screen RAM.** The game can be alive and wrong; it can also look right while the PC is anywhere.
- The remote monitor is entered by any input while the machine runs; a poll interrupts the emulation briefly. Keep polls few (`--feed` only when needed).
- `timeout` killing VICE leaves no screenshot; give `-limitcycles` or the script's `--timeout` generous limits.
- Several VICEs at once need different monitor ports (`--port` / `VICE_MONITOR_PORT`); a leftover x64sc holds its port. Kill by PID, not `pkill -f` with a pattern that is in your own command line.
- x64sc opens a window unless a display is missing; the scripts do not hide it. On a machine without a display use a virtual one (`xvfb-run`): not tried here.
- A plain PRG spanning `$D000-$DFFF` is fine for VICE autostart injection; a real KERNAL `LOAD` writes into VIC/CIA there, so a disk build needs a packed PRG.

## Proven and not proven
Proven (on one game: a REM-cracked 1541 disk with a three-stage unpacker, one key wait before the menu, one prompt answered by a key press):
- the hand-off dump taken unattended matches the one made by the project's own earlier script in every byte of the game range and differs from it, and from a second unattended run, only in the six non-game bytes listed above;
- the stage 1 and stage 2 specs reproduce both recorded SHA-256 values of the reference exactly;
- the screenshot judge passes a smoke screenshot of the launcher build at 1.00 and fails a same-size image with the crop blanked (0.72) and a different-size image (-1).
Not proven: NTSC media, tape media, fast-loader media that need more than a key wait, a game that loads code after the hand-off (stage 2 item 5 of the playbook), `--io` output used to build a launcher, running without a display, the `--feed` loop on a prompt other than a key press, `copy` from a second release whose hand-off state differs from the first.

## Voting out emulator noise, and the Ghidra step
- `scripts/reference/vote_dumps.py --out VOTED.bin DUMP DUMP DUMP ...`: majority vote per byte over several dumps taken at the same moment (`vice_handoff.py --no-warp` for real speed). Reports positions without a majority inside the game range (take more dumps, or check whether a later step overwrites them).
- `scripts/ghidra/make_seeds.py`, `run.sh`, `setup.py`: seeds from evidence, then headless import, seeding and Kick Assembler export; see `new_game.md` stage 5.
- `c64trace --selftest DUMP_BEFORE DUMP_AT_HANDOFF --selftest-pc ... --selftest-done HANDOFF` cross-checks a depacker (stage 2).
