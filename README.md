# MOSaic

*MOS AI deCompiler*

Turn a Commodore 64 game's disk or tape image into byte-identical, fully commented, relocatable [Kick Assembler](http://theweb.dk/KickAssembler/) source, one piece of evidence at a time.

MOSaic is a Claude Code skill: a process, its rules, and the scripts that check them.

## What's in it

- `SKILL.md`, `references/`: the process (acquire, phase 1, phase 2), the rules, and the decision log
- `scripts/`: refactoring tools, checks, a 6510 tracer, a routine-test simulator, graphics renderer, Ghidra and VICE glue
- `templates/`, `framework/`, `libs/`: project scaffold, byte-identity gate, C64 hardware definitions

## How it works

1. **Research first.** The game's manual, release databases, wikis, reviews and POKE lists are read before any code, and recorded as unconfirmed leads in `docs/gameplay.md`. Scanned manuals are rendered to images and read. Nothing from the web goes into the source until the code confirms it.
2. **Start from the original medium.** A disk or tape image sits in a read-only `originals/` folder and is never attached to an emulator directly: VICE runs a scratch copy. A tape's standard loader is decoded to files, and a turbo loader is run in VICE or decoded by a script written for it.
3. **Find the hand-off and derive a clean reference.** The game runs to the point where it is fully loaded and about to start. RAM is dumped there several times and the dumps are voted on to cancel emulator noise. Loader and crack bytes are zeroed only when the tracer proves nothing touches them. The result is a game-only image with a recorded SHA-256.
4. **Disassemble from evidence.** A small 6510 tracer records what executes. Those addresses seed Ghidra for the first split of code and data, and an exporter writes Kick Assembler source that assembles to the identical image.
5. **Phase 1: understand everything while the build stays byte-identical.** `just verify` is the gate. Agents work in scratch copies called slices, merged only after their checks pass, with progress notes while they run.
6. **Names need proof.** A name that claims a role needs the code and an observation from a tracer run. What a thing is to a player goes to the owner, with a picture rendered in the game's own colours and modes. Answers are recorded so nobody asks twice.
7. **Rules are enforced by scripts.** About twenty checks cover raw addresses, placeholders, echo comments, list end markers, one record per row, banners that tile the image, table sizes, hardware-dependency tags and unreferenced blocks. A source is complete only when the report says so.
8. **Phase 2 begins with a safety net.** Routine tests run the original code in a simulator against Python models. Golden traces record the game's state per frame under scripted input, with a timing-tolerant set for when bytes change.
9. **Then it refactors in small, gated steps.** The source is split into files, a platform interface is defined with written contracts, layout assumptions become asserts and a relocation sweep, and approved dead blocks are removed without moving live code. The gate then accepts a difference only inside the approved ranges.

## See results

In a project made with MOSaic (`new_project.py`), every command takes the phase: `1` is the frozen, byte-identical reconstruction, `2` is the split, refactored source. With no argument it uses `ACTIVE_PHASE` from `project.config`.

```
just verify        # assemble and compare byte for byte with the original image: the gate
just smoke         # boot it headless in VICE and check the screen against a reference picture
just launch        # run it in VICE at real speed, symbols loaded
just check         # everything that must stay green: verify, tests, golden traces
just verify 1      # name the phase: 1 or 2
just --list        # every command with its description
```

`docs/` in the project holds the pictures the process produces (`docs/gfx/`), the answers recorded from the game's owner, and for phase 2 the file map (`docs/phase2_files.md`).

## Use

Link it as a skill, then scaffold a project:

```
ln -s "$PWD" ~/.claude/skills/c64-decomp
python3 scripts/check_env.py
python3 scripts/new_project.py --help
```

Needs Python 3, Java 17+, Kick Assembler, git and [`just`](https://github.com/casey/just). VICE, Ghidra, a C compiler, and Pillow are needed for some steps; `check_env.py` reports what each role requires. Developed on Linux; macOS should work; on Windows use WSL.

## Tests

```
python3 -B scripts/selftest_tools.py
python3 -B scripts/refactor/selftest.py
python3 -B scripts/render/selftest.py
python3 -B scripts/tape/selftest.py
```

## Licence

MIT (see `LICENSE`): use it freely, all care and no responsibility, with no warranty and no liability.
