# Phase 1 method: understanding unfamiliar code
Applies to: every project, from the first byte-identical build to `p1_complete.py` clean. The rules say what the result must look like (`rules.md`, `naming.md`); this page is how to get there. It is a first version written from the process, to be refined by the first runs that follow it.

## 1. Orient from evidence
Start at the entry the hand-off found. Use the tracer's output from the entry (`scripts/trace`: executed edges, hit counts, interrupt entries, which bytes were executed, read or written) to find the skeleton: **initialisation, the main loop, the interrupt chain, the per-frame work**. Disassembly alone cannot tell code from data or what actually runs.

## 2. Map the subsystems before naming leaves
`scripts/platform_deps.py` groups routines by the hardware registers they touch (input, video, sound, timers). Sort routines into: input, game state update, drawing, sound, level or data loading, utilities used everywhere. Name the **utilities and leaf routines first** (small, called often, easy to prove), then work up.

## 3. Turn the documents into hypotheses (`research.md`, `docs/gameplay.md`)
Take each documented mechanic and say what it must look like in code: a joystick read of CIA 1 port A, a per-frame countdown for a timer, a counter compared against 100 for an extra life, a table of values for scoring, a routine that runs once per level. Search for that shape; do not name something because a document says it exists.

## 4. The evidence ladder (a name is provisional until the top rung)
1. **Seen in the disassembly** (what the instructions do): enough for a descriptive name built from the facts (`row_pointer_lo`, `counter_decremented_each_frame`).
2. **Seen executing** (tracer hits, edges): it really runs, how often, from where.
3. **Seen behaving as hypothesised** (a write watch over a run, a value that changes as the documents say, a breakpoint in the emulator): enough for a name that claims a role (`lives`, `time_remaining`).
4. **Confirmed by the user** (what a sprite or a sound IS, an ambiguity): the only rung for names that claim a meaning nobody can prove from code.
Mark anything below rung 3 with `TODO(name)` (provisional) and anything only the user can settle with `TODO(user)`. **Never invent a meaning.**

## 5. Data versus code, tables, self-modifying code
The tracer's flags separate executed bytes from bytes only read (tables, graphics, text) and bytes written (variables, buffers, self-modified code: executed and written). A table has a stride and an index register: find who reads it with which index. Pointer tables become `.word label`. Text is written as text (`rules.md`).

## 6. The work loop
Per routine or section: read, name, add the section banner, comment (the comment rules), replace raw operands with labels, `just verify` (byte-identical), commit. Small commits; the gate is never red at a commit. Track `p1_complete.py` as the progress number. Keep a log (`docs/phase1_log.md`): order, evidence used, questions for the user.

## 7. Things that go wrong
- Naming by pattern (renaming every `lda #0 / sta x` the same way) without checking each.
- Treating a document's POKE address as proof.
- Descending into a subsystem before its callers are understood: stop, give it a provisional name and a `TODO(name)`.
- Changing a byte while renaming: names may change, bytes may not.
