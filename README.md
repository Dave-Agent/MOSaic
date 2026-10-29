# MOSaic

*MOS AI deCompiler*

Turn a Commodore 64 game's disk or tape image into byte-identical, fully commented, relocatable [Kick Assembler](http://theweb.dk/KickAssembler/) source, one piece of evidence at a time.

MOSaic is a Claude Code skill: a process, its rules, and the scripts that check them.

## What's in it

- `SKILL.md`, `references/`: the process (acquire, phase 1, phase 2), the rules, and the decision log
- `scripts/`: refactoring tools, checks, a 6510 tracer, a routine-test simulator, graphics renderer, Ghidra and VICE glue
- `templates/`, `framework/`, `libs/`: project scaffold, byte-identity gate, C64 hardware definitions

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
