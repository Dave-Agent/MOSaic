# HOWTO: from a game's disk or tape file to a finished phase 2

**How to read this.** Every step has two ways to do it, side by side:

- **Guided:** you tell Claude what to do (or run the setup script) and it does the work. You can always just say **"move to the next stage"**.
- **Manual:** the commands, if you want to run them yourself or see what the agent runs.

Pick a side for each step; you can mix them. `just status` in the project always tells you which step you are on.

**Words used below.**
**Reference:** a memory image of the game alone (no loader, no crack), made in step 4; every build is checked against it. **Hand-off:** the moment the game is fully loaded and about to start. **Byte-identical:** the source assembles to exactly the same bytes as the reference. **Slice:** one region of the source worked on in a scratch copy, merged back when its checks pass. **Agent:** the Claude session doing the work, in Claude Code inside the project folder.
**Phase 1** turns the game into one fully commented source file that is byte-identical to the original. **Phase 2** splits it into files, separates the game from the C64 hardware, and makes it relocatable.

---

## Step 0. Set up your machine (once)

**Goal:** the tools are installed and the skill is linked into Claude Code.

First install these (both ways need them). Use your package manager where there is one.

| Tool | For | Where |
|---|---|---|
| Python 3, Java 17+, git, a C compiler | running the scripts, assembling, history, the tracer | your package manager |
| Kick Assembler | assembling | theweb.dk/KickAssembler: put `KickAss.jar` in `~/tools/` |
| `just` | the project's commands | github.com/casey/just |
| VICE (`x64sc`) with its C64 ROMs | running the game, memory dumps | your package manager |
| Ghidra 11+ | the first disassembly | ghidra-sre.org: unzip in your home folder |
| Claude Code | the agent you talk to | claude.com/claude-code |

| Guided | Manual |
|---|---|
| `git clone https://github.com/Dave-Agent/MOSaic.git ~/MOSaic`<br>`cd ~/MOSaic`<br>`./setup.sh`<br><br>It links the skill, checks the tools and offers to create your first project (step 1). It installs nothing itself. `./setup.sh --check` only checks the tools. | `mkdir -p ~/.claude/skills`<br>`ln -s ~/MOSaic ~/.claude/skills/mosaic`<br>`python3 ~/.claude/skills/mosaic/scripts/check_env.py --role run --role trace --role ghidra`<br><br>The link must be called `mosaic`: the commands in this guide use that path. |

**Done when:** the check ends with `all required tools present`.

---

## Step 1. Add the game

**Goal:** a project folder holding your copy of the game's disk or tape file (`.d64`, `.g64` or `.tap`; a copy with the copy protection removed is best).

| Guided | Manual |
|---|---|
| Run `./setup.sh` and answer **yes** to "Create a project now?". It asks for the game's file, its name and the project folder, then creates it.<br><br>(Step 0 already did this if you said yes there.) | `python3 ~/.claude/skills/mosaic/scripts/new_project.py --root ~/C64Projects/MyGame --name "My Game" --media ~/Downloads/mygame.d64`<br>`cd ~/C64Projects/MyGame`<br>`just env`<br>`just status`<br><br>`--root` is the new project folder, `--name` the game's name, `--media` your game file. Add `--protect` to make the copy read-only. |

Your file is copied into the project's `originals/` folder and its SHA-256 recorded. The original is never modified and never loaded into an emulator directly; VICE only runs temporary copies.

**Done when:** `just status` says `NEXT: step 2`.

---

## Steps 2 to 8: one run, from research to a game that starts

These seven steps are one continuous job and there is no point at which you would want to stop. Ask for them once and the agent works through all of them, telling you each step as it starts. It stops early only if it needs something from you: a decision, a missing tool, or a failure it cannot resolve.

**To start the whole run, say:** "Use the MOSaic skill. Acquire this game: work through HOWTO steps 2 to 8, from research to a game that starts, without stopping between them."

**Do not type in the VICE window** while it dumps memory (step 4). A disk takes minutes; a tape longer. When it finishes you have a build that is byte-identical to the original and that you have seen start, and the agent asks whether to begin phase 1.

The steps below say what happens in each, and the commands if you want to run any of them yourself.

---

## Step 2. Research the game

**Goal:** the game's documented behaviour written down as unconfirmed leads.

| Guided | Manual |
|---|---|
| Open Claude Code in the project folder and give the run prompt above (this step is where the run starts).<br><br>The agent reads the manual, release databases, wikis, reviews and POKE lists, and writes the two files. Nothing from the web goes into the code until the code confirms it. | Write `docs/gameplay.md` (one row per documented fact: what the documents say, the source, status) and `docs/background.md` (history, releases) yourself.<br><br>Method: `references/research.md`. For a scanned manual: `scripts/research/pdf_pages.py FILE.pdf --out DIR`. |

**Done when:** both files are filled in.

---

## Step 3. Extract the files and work out the boot chain

**Goal:** every file out of the image, and the chain that loads the game written down.

| Guided | Manual |
|---|---|
| Part of the run you started in step 2; nothing to say.<br><br>The agent extracts the files, disassembles the boot stub, works out what loads what, and writes `docs/boot_analysis.md`. A tape with a turbo loader needs a decoder written for that loader; the agent will say so. | Disk:<br>`python3 ~/.claude/skills/mosaic/scripts/disk/extract_files.py originals/game.d64 --out extracted/`<br>Tape:<br>`python3 ~/.claude/skills/mosaic/scripts/tape/tap_extract.py originals/game.tap --out extracted/`<br>Then read the boot stub with `scripts/disasm/dis6502.py` (see `--help`) and write `docs/boot_analysis.md`. |

**Done when:** `docs/boot_analysis.md` names the boot chain and the address where the game starts (the hand-off).

---

## Step 4. Derive the clean reference

**Goal:** a memory image of the game alone, with a recorded SHA-256.

| Guided | Manual |
|---|---|
| Part of the run you started in step 2; nothing to say.<br><br>The agent runs the game in VICE (a scratch copy), dumps RAM at the hand-off several times, votes out emulator noise, and zeroes loader and crack bytes only where the tracer proves the game never touches them.<br><br>**Do not type in the VICE window while it runs.** | In `project.config` set `DUMP_PC`, `HANDOFF_PC` and `REF_KEEP` (the hand-off address and the memory range to keep), list what to zero in `tools/reference.spec`, then:<br>`just derive`<br><br>(`just dumps`, `just vote`, `just decrunch`, `just reference` are its parts.) |

**Done when:** `reference.sha256` exists and `docs/` says where the reference came from.

---

## Step 5. Export the disassembly from Ghidra

**Goal:** Kick Assembler source for the whole reference, from the tracer's evidence and Ghidra.

| Guided | Manual |
|---|---|
| Part of the run you started in step 2; nothing to say.<br><br>The tracer runs the game and records which addresses execute; Ghidra follows the code from those addresses and the exporter writes the source. The exporter script downloads itself the first time. | `just seeds`<br>`just ghidra`<br><br>The result lands in `ghidra/`; it is not yet your source. |

**Done when:** `ghidra/<name>.asm` and `ghidra/<name>_Symbols.asm` exist.

---

## Step 6. Get the first byte-identical build

**Goal:** your own copy of the source assembles to exactly the reference.

| Guided | Manual |
|---|---|
| Part of the run you started in step 2; nothing to say.<br><br>The agent copies the export into `phase1/src/`, points the project at it and runs the gate. If it fails it works through the usual first differences in `references/new_game.md`. | `cp ghidra/<name>.asm phase1/src/<name>.asm`<br>`cp ghidra/<name>_Symbols.asm phase1/src/symbols.asm`<br>Fix the `#import` line at the top of the main file to say `symbols.asm`, set `SRC_MAIN="phase1/src/<name>.asm"` in `project.config`, then:<br>`just verify` |

**Done when:** `just verify` prints `PASS: built image is byte-identical`. From now on it is the gate: it must pass before every commit.

---

## Step 7. Name the hardware registers

**Goal:** raw register addresses become `VIC.`, `CIA.` and `SID.` names, and short local labels become anonymous.

| Guided | Manual |
|---|---|
| Part of the run you started in step 2; nothing to say.<br><br>The agent runs both conversions and verifies after each. | `just libs-apply`<br>`just verify`<br>`just anon-apply`<br>`just verify` |

**Done when:** `just verify` still passes and `just status` shows step 7 done.

---

## Step 8. Start the game

**Goal:** you have seen the build run.

| Guided | Manual |
|---|---|
| Part of the run you started in step 2; nothing to say.<br><br>The agent boots the build headless in VICE, takes a screenshot (the first run creates `tools/smoke_ref.png`) and looks at it to confirm it is the game and not a blank or BASIC screen. | `just smoke`<br>`just launch`<br><br>`just launch` runs it in VICE at real speed. Some games jam on a fraction of starts; if the original does, keep it and set `SMOKE_RETRIES` in `project.config` (the agent records it in `docs/gameplay.md`). |

**Done when:** `just smoke` passes and you have watched the game start.

---

## Step 9. Phase 1: understand every routine

**Goal:** every routine named and commented, no raw address operands, no placeholder names, still byte-identical.

| Guided | Manual |
|---|---|
| Say:<br>"Start phase 1 following `references/phase1_method.md`. Work in slices, and ask me what a thing is only after trying the code and a tracer run."<br><br>The agent names things from evidence only (the code plus a tracer observation). It **asks you** one question at a time about what a thing is to a player, with a picture, and records each answer in `docs/user_answers.md`. It never asks what the code does. | `just comment-check` (then `comment_check.py --fix` to tidy the export)<br>`just gfx` (sprites and characters into `docs/gfx/`)<br>A slice:<br>`just slice-start NAME`<br>work in `/tmp/mosaic-slices/NAME/project`<br>`just slice-check`<br>`just slice-merge NAME`<br>`just slice-status` shows progress.<br>How much remains:<br>`python3 ~/.claude/skills/mosaic/scripts/p1_complete.py --root . --phase 1` |

**Done when:** the report says `VERDICT: COMPLETE`, `just verify` and `just smoke` pass. Run `git tag p1-byte-identical` and play the game once.

---

## Phase 2: a source ready for a port

Phase 2 works on a copy of phase 1. After this, every command takes the phase: `just verify 2`, `just check 2`, `just launch 2`. Read `references/phase2_split.md` and `references/phase2_port.md` first.

## Step 10. Build the safety net

**Goal:** tests and recorded traces that prove the game still behaves the same while the source changes.

| Guided | Manual |
|---|---|
| Say "Start phase 2: the copy, then the safety net and the hardware catalogue."<br><br>The agent writes routine tests (code run in a simulator against Python models), golden traces (the game's state per frame under scripted input), `docs/platform_layer.md` and `docs/phase2_plan.md`. | `rsync -a --exclude build --exclude '*.sym' phase1/src/ phase2/src/`<br>In `project.config`: `PHASE2_MAIN="phase2/src/<name>.asm"` and `ACTIVE_PHASE="2"`.<br>Write tests in `tools/tests/` and scenarios in `tools/golden/`, then:<br>`just test 1`<br>`just golden-record`<br>`just golden 1` |

**Done when:** `just check 1` passes.

## Step 11. Split the source into files (still byte-identical)

**Goal:** the one big file becomes files under `game/`, `platform/` and `data/`.

| Guided | Manual |
|---|---|
| Say "move to the next stage".<br><br>The agent moves each section into its own file and runs the gate after every move. | Write a plan file (one line per file: `DIR` tab `SECTION` tab `NAME`), then:<br>`python3 ~/.claude/skills/mosaic/scripts/split_all.py PLAN`<br>Cut inside a section: `scripts/cut_section.py`.<br>`just verify 2` after every move. |

**Done when:** the phase 2 main file is only imports and `just verify 2` is byte-identical.

## Step 12. Define the platform interface

**Goal:** the hardware-facing routines live in namespaces (`Input`, `Time`, `Sound`, `Gfx`, `Storage`, `Boot`) with written contracts.

| Guided | Manual |
|---|---|
| Say "move to the next stage".<br><br>The agent does it one subsystem at a time, byte-identical. Where a wrapper would cost bytes or cycles in a full image it leaves the access alone, tags it `TODO(port)` and says why. | Move the routines into namespaces, write each contract in `docs/porting.md` (inputs, outputs, what is preserved, interrupt safety), then:<br>`just check 2` |

**Done when:** `docs/porting.md` exists and `just check 2` passes.

## Step 13. Make it relocatable

**Goal:** proof that code and data can move without changing behaviour.

| Guided | Manual |
|---|---|
| Say "move to the next stage".<br><br>The agent resolves each relocation hazard, turns layout assumptions into `.assert`s, and runs the layout sweep with a control variant that changes no address. Findings go in `docs/relocation_hazards.md`. | `just reloc 2`<br>`just fuzz-layout ...` (options in `references/testing.md`, "Moving the layout")<br>Always include a control variant. |

**Done when:** every hazard is resolved or documented and the sweep shows no address dependency.

## Step 14. Remove the dead code

**Goal:** the unused blocks are gone, and the gate proves nothing else changed.

| Guided | Manual |
|---|---|
| Say "move to the next stage".<br><br>The agent lists every dead block with its size. **You decide which may go**; it records your answer in `docs/user_answers.md`. It removes each approved block leaving a hole, so nothing else moves, and records any bugs of the original it finds (kept, not fixed). | List the removed address ranges in `tools/removals.txt` (one `LO-HI` hex range per line) and set `PHASE2_ALLOWED_DIFF="tools/removals.txt"` in `project.config`. Then:<br>`just verify 2`<br>`just check 2`<br>`just smoke 2`<br>`just launch 2` |

`just verify 2` now passes only when every changed byte is inside the listed ranges.

**Done when:** all four commands pass and **you have played it** with `just launch 2`.

---

## What you have at the end

- `phase1/src`: one commented, byte-identical source (frozen).
- `phase2/src`: the same game in namespaced files with a platform interface, relocation asserts and the dead code removed.
- `docs/`: the research, the boot analysis, your recorded answers, the pictures, the porting contracts, the relocation hazards and the list of removals.
- Commands that always work: `just verify`, `just check`, `just smoke`, `just launch`, `just status`.

**If something goes wrong:** run `just status` and read the evidence it prints. The detailed references are `references/new_game.md` (steps 1 to 8), `phase1_method.md` (step 9), `phase2_split.md` and `testing.md` (steps 10 to 14).
