# Phase 1 method: understanding unfamiliar code
Applies to: every project, from the first byte-identical build to `p1_complete.py` clean. The rules say what the result must look like (`rules.md`, `naming.md`); this page is how to get there. It is a first version written from the process, to be refined by the first runs that follow it.

## 0. Choose and bound a slice
Phase 1 on a real game is far too big for one pass. Work in **slices**: a coherent region you can finish properly (every name, comment and operand in it clean) rather than a thin pass over everything. Start with the entry, initialisation, main loop and interrupt chain: the tracer has seen them run, and everything else hangs off them. **Stop descending at a clear subsystem boundary**: a routine that has its own data, many callers, or is never reached from the entry in the tracer run. Give it a descriptive provisional name and a `TODO(name)`, note it in the log, and leave its insides for a later slice. A slice is "done" when `p1_complete.py --range LO-HI` shows no unmarked placeholder and no raw operand in it; marked provisional names are honest and allowed to remain.

## 1. Orient from evidence
Start at the entry the hand-off found. Run `scripts/trace/report.py` on the coverage run first (interrupt entries with their raster lines, the hottest loops, JSR callers, input reads, self-modified and data ranges). Use the tracer's output from the entry (`scripts/trace`: executed edges, hit counts, interrupt entries, which bytes were executed, read or written) to find the skeleton: **initialisation, the main loop, the interrupt chain, the per-frame work**. Disassembly alone cannot tell code from data or what actually runs.

## 2. Map the subsystems before naming leaves
`scripts/platform_deps.py` groups routines by the hardware registers they touch (input, video, sound, timers). Sort routines into: input, game state update, drawing, sound, level or data loading, utilities used everywhere. Name the **utilities and leaf routines first** (small, called often, easy to prove), then work up.

## 3. Turn the documents into hypotheses (`research.md`, `docs/gameplay.md`)
Take each documented mechanic and say what it must look like in code: a joystick read of CIA 1 port A, a per-frame countdown for a timer, a counter compared against 100 for an extra life, a table of values for scoring, a routine that runs once per level. Search for that shape; do not name something because a document says it exists.

## 4. The evidence ladder (a name is provisional until the top rung)
1. **Seen in the disassembly** (what the instructions do): enough for a descriptive name built from the facts (`row_pointer_lo`, `counter_decremented_each_frame`).
2. **Seen executing** (tracer hits, edges): it really runs, how often, from where.
3. **Seen behaving as hypothesised** (a write watch over a run, a value that changes as the documents say, a breakpoint in the emulator): enough for a name that claims a role (`lives`, `time_remaining`).
4. **Confirmed by the user** (what a sprite or a sound IS, an ambiguity): the only rung for names that claim a meaning nobody can prove from code.
**Rung 3 for state machines and roles, with two examples.** A document that says the game has the thing, plus behaviour seen in a *controlled* tracer run, is rung 3 and allows a role-claiming name: hold an input for N frames, sample the variables per frame (`scripts/trace/sample_report.py`, input changes with `--joy2-at`) and read what changed. Example A, a counter: a documented patch targets its decrement, it is set at the turn start and decremented once when a turn ends: `lives`. Example B, a state byte: the manual says there is a jump; with up held the sprite's Y falls from one value to another and back over 71 frames while a state byte reads `$80`, then `$FF`, then 0: `jump_state` (0 = none, `$80` = rising, `$FF` = coming down). A name needs the document **and** the observation; either alone is rung 1 or 2. User confirmation is for what code cannot show: what a sprite or a sound IS, what a key combination is for, why something is done. A variable the controlled runs never exercised stays neutral with `TODO(name)`. Rung 3 is usually one `trace/sample_report.py` run under a fixed or scripted input (`--joy2-at`, `--keymat-at`); quote the frames and values in the log.

Mark anything below rung 3 with `TODO(name)` (provisional) and anything only the user can settle with `TODO(user)`. **Never invent a meaning.**

## 4b. The variable-role protocol
A variable's role comes from **all of its readers and writers**, not from the first place you see it. For each unknown variable list every instruction that reads it and every one that writes it (`scripts/refactor/uses.py NAME`: readers and writers per routine, in-stream labels and offsets included), with the routine each is in, and write down: who initialises it, who changes it and how (increment, set, mask), who tests it and what that decides. Name it for what that proves (`xscroll_main_band`: ORed into `$D016` by one handler and decremented by the scroll code) and no more. Two variables with the same shape (a `_p1`/`_p2` pair) are a table with an index: look for the index. `refactor/uses.py` shows the enclosing routine (scope, else the nearest `jsr` / `jmp`-from-elsewhere target; `--flags PREFIX` adds what the tracer saw called) and the nearest label: the routine is the unit of the protocol.

**When a document and the code disagree** (a manual says five lives, the code starts a counter at 3; a wiki says 100 seconds, the countdown is 4:1 units of 41 frames), do not pick a side and do not force the name: record both in `docs/gameplay.md` (status `conflicts`), name the item neutrally, and put the question under `TODO(user)`. A conflict is information (a different unit, a different item, a bug, a different version).

## 5. Data versus code, tables, self-modifying code
The tracer's flags separate executed bytes from bytes only read (tables, graphics, text) and bytes written (variables, buffers, self-modified code: executed and written). A table has a stride and an index register: find who reads it with which index. Pointer tables become `.word label`. Text is written as text (`rules.md`).

## 5b. The order of passes (each one `just verify`-green, one commit each)
1. Baseline: `p1_complete.py` numbers; the libs applied (`apply_libs.py`); the label files split (`symbols_tidy.py`).
2. Rename map: the names you have proven (a TSV of old to new, applied everywhere in code and label files by a script: names only).
3. Variables and tables inside the image become in-stream labels; SMC operands become `label:operand`. Pointer data: `addr_tables.py [--range]` lists candidate pointer tables with targets and labels (heuristic: read the table and its indexer); `add_label.py --map` adds the missing labels; `refactor/table_words.py` converts `word` / `field` / `lo` / `hi` tables with byte identity checked per entry.
4. Raw address operands become names (by map); address pairs become `#<label` / `#>label`.
5. Strings become text (`kick.md`, custom encoding); tables get their column-list block comments.
6. Routines become scopes; local labels get meaningful names or the anonymous form (`rules.md`).
7. Comment alignment, then block comments, section banners and `TODO` markers; the log.
Mechanical passes first, prose last: a rename after the prose is written means rewriting the prose. The tools for each pass are in `scripts/refactor/` (`rename`, `move_img`, `drop_labels`, `replace_raw`, `replace_imm`, `scopeify`, `anon_labels`, `set_comment`); call a slice clean with `p1_complete.py --range LO-HI --allow-marked`.

**Image variables to in-stream labels.** A Ghidra `.label DAT_xxxx = $ADDR` that lies inside the image becomes `name:` in the stream at that address (an instruction, or a split `.byte` row); the XREF text travels with it; an SMC operand byte becomes `label:operand`, its high byte `label+1`. `move_img.py` does this from a map. A label that lands inside a `.byte` row it cannot split cleanly is fixed by hand.

## 6. The work loop
Per routine or section: read, name, add the section banner, comment (the comment rules), replace raw operands with labels, `just verify` (byte-identical), commit. Small commits; the gate is never red at a commit. Track `p1_complete.py` as the progress number. Keep a log (`docs/phase1_log.md`): order, evidence used, questions for the user. `todo_list.py [--range]` lists the `TODO(user|name|block)` markers with label and routine for the log and the questions to the user. `p1_complete.py` always ends with `VERDICT: COMPLETE | SLICE CLEAN | NOT COMPLETE` (a slice is never called COMPLETE); with `--range` it also reads data rows, and a range with no instruction line is judged by its checks 5 and 6 and by reading.

**Music / sound data.** Describe a sound driver by the registers it writes and the tables it reads. Name per-voice arrays by the SID register or the record byte they hold. Use the position-advance rate as the rung-3 check of the tick period. Leave what a song or effect IS as `TODO(user)`/`TODO(sound)`.

**Corrections to earlier work.** When your reading contradicts a comment or a name from an earlier slice (a routine described as moving sprites 7 down to 2 that moves 7 down to 3; a routine called a keyboard scan that is the frame dispatcher), fix it in the same commit and list it in the log under "Corrections". An earlier slice's text is evidence, not authority.

## 7. Things that go wrong
- Naming by pattern (renaming every `lda #0 / sta x` the same way) without checking each.
- Treating a document's POKE address as proof.
- Descending into a subsystem before its callers are understood: stop, give it a provisional name and a `TODO(name)`.
- Changing a byte while renaming: names may change, bytes may not.
