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
4. **Dynamic and static analysis together.** A small 6510 tracer runs the game and records what really executes. Ghidra then follows the code statically from those addresses, separates code from data and records who references what, and an exporter writes Kick Assembler source that assembles to the identical image. Execution tells the analysis where to start; the static pass finds what the run didn't reach.
5. **Phase 1: understand everything while the build stays byte-identical.** `just verify` is the gate. Agents work in scratch copies called slices, merged only after their checks pass, with progress notes while they run.
6. **Names need proof.** A name that claims a role needs the code and an observation from a tracer run. What a thing is to a player goes to the owner, with a picture rendered in the game's own colours and modes. Answers are recorded so nobody asks twice.
7. **Rules are enforced by scripts.** About twenty checks cover raw addresses, placeholders, echo comments, list end markers, one record per row, banners that tile the image, table sizes, hardware-dependency tags and unreferenced blocks. A source is complete only when the report says so.
8. **Phase 2 begins with a safety net.** Routine tests run the original code in a simulator against Python models. Golden traces record the game's state per frame under scripted input, with a timing-tolerant set for when bytes change.
9. **Then it refactors in small, gated steps.** The source is split into files, a platform interface is defined with written contracts, layout assumptions become asserts and a relocation sweep, and approved dead blocks are removed without moving live code. The gate then accepts a difference only inside the approved ranges.

## Getting started

The full step-by-step, from adding the game's image to a finished phase 2, is in [HOWTO.md](HOWTO.md). The short version:

**(a) Install the tools.** Python 3, Java 17+, [Kick Assembler](http://theweb.dk/KickAssembler/) (the jar in `~/tools/KickAss.jar`, or set `KICKASS_JAR` in `project.config`), git, [`just`](https://github.com/casey/just), VICE (`x64sc`) with its C64 ROMs, Ghidra 11+ (set `GHIDRA_HOME` if it isn't under `~/ghidra*`) and a C compiler. The Ghidra exporter script is fetched automatically on first use. Pillow is needed for pictures. Developed on Linux; macOS should work; on Windows use WSL.

**(b) Get the skill and run the setup script.** It links the skill into Claude Code, checks your tools, and offers to create a project for your game, asking for its name and file:
```
git clone https://github.com/Dave-Agent/MOSaic.git ~/MOSaic
cd ~/MOSaic
./setup.sh
```
It changes only `~/.claude/skills/mosaic` and the project folder you name, and installs nothing. `./setup.sh --check` only checks the tools. The manual commands are in [HOWTO.md](HOWTO.md), steps 0 and 1.

**(c) Check the project** it created, then continue:
```
cd ~/C64Projects/MyGame
just status
```
The original game file was copied into the project's `originals/` folder with its SHA-256. It is never modified and never attached to an emulator directly; VICE only runs scratch copies. MOSaic creates a local git repository in the project and commits after each step. It never pushes.

**(d) Open Claude Code in the project folder and ask for the first stage.**
> Use the MOSaic skill. Research this game, then continue to the first byte-identical build.

The agent researches the game, extracts the files, finds the point where the game is fully loaded, derives a clean reference image, exports the disassembly from Ghidra, and builds it back byte for byte. A disk takes tens of minutes and a tape longer. VICE opens windows while it dumps memory; don't type in them.

**(e) Tell it to continue when it stops.** The agent finishes the task it was given and stops at each stage boundary. It runs `just status`, tells you what was done and what the next stage is, and asks whether to continue. You can also just say "move to the next stage" (or "what's next?"): it works out the stage from the project, tells you which step it is starting and what it will do, and gets on with it without asking again. The prompts below are what each stage amounts to, for when you want to be specific:

| When the agent says… | Ask |
|---|---|
| the Ghidra export is done | "Continue from stage 5 of `new_game.md`: copy the export into `phase1/src/`, set `SRC_MAIN`, get `just verify` byte-identical, run `just libs-apply` and `just anon-apply`, check the game starts with `just smoke`, and report the `p1_complete` backlog." |
| the first build passes | "Start phase 1 following `references/phase1_method.md`: work in slices, ask me what a thing is only after trying the code and a tracer run, and report progress." |
| phase 1 is complete | "Start phase 2 following `references/phase2_split.md`." |

**(f) Check where you are** with `just --list` for the commands, `python3 ~/.claude/skills/mosaic/scripts/p1_complete.py --root . --phase 1` for how much of phase 1 remains, and `docs/` in the project for the research, the boot analysis and the answers recorded from you.

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

## Known limitations

- Commodore 64 only: the hardware libraries, the tracer and the VICE glue are C64-specific.
- Disk images are read with `c1541`. A tape's standard-format files are decoded; a turbo or custom tape loader needs a decoder written for that loader (`tap_extract.py` extracts the stub, reports the rest, and the hand-off dump from VICE gets the game itself). Cartridge images are not handled.
- The reference comes from a medium with the copy protection removed; analysing a protected original is manual work.
- The tracer is not a full emulator: it does not draw sprites or characters, model collisions, or produce SID output. Checking pictures and sound needs VICE, and the game's owner.
- The relocation sweep compares the program's state and its timing; it cannot see where data the VIC reads sits.
- Naming what a thing is to a player needs someone who knows the game; without one, names stay descriptions of what the code does.

## Tests

```
python3 -B scripts/selftest_tools.py
python3 -B scripts/refactor/selftest.py
python3 -B scripts/render/selftest.py
python3 -B scripts/tape/selftest.py
```

## Licence

MIT (see `LICENSE`): use it freely, all care and no responsibility, with no warranty and no liability.
