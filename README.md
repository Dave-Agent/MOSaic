# MOSaic

Turn a Commodore 64 game's disk image into byte-identical, fully commented, relocatable [Kick Assembler](http://theweb.dk/KickAssembler/) source, one piece of evidence at a time.

MOSaic is a Claude Code skill: a written process, a rule set, and the scripts that enforce it. It contains no game data.

## What's in it

- `SKILL.md`, `references/`: the process (acquire, phase 1, phase 2), the rules, and the decision log
- `scripts/`: refactoring tools, checks, a 6510 tracer, a routine-test simulator, graphics renderer, Ghidra and VICE glue
- `templates/`, `framework/`, `libs/`: project scaffold, byte-identity gate, C64 hardware definitions

## Use

Link it as a skill, then scaffold a project:

```
ln -s "$PWD" ~/.claude/skills/c64-decomp
python3 scripts/check_env.py
python3 scripts/new_project.py --help
```

Needs Python 3, Java 17+, Kick Assembler, git and [`just`](https://github.com/casey/just). VICE, Ghidra, a C compiler, and Pillow are needed for some steps; `check_env.py` reports what each role requires.

## Tests

```
python3 -B scripts/selftest_tools.py
python3 -B scripts/refactor/selftest.py
python3 -B scripts/render/selftest.py
python3 -B scripts/tape/selftest.py
```
