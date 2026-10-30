# HOWTO: from a game's disk or tape file to a finished phase 2

Five steps after setup. Steps 2 and 4 are big jobs that the agent does in the background in several parts; you ask for each once and it tells you the part it is on. The parts are listed in the appendices for anyone who wants the detail.

**How to read this.** Every step has two ways to do it, side by side:

- **Guided:** you tell Claude what to do (or run the setup script) and it does the work. You can always just say **"move to the next stage"**.
- **Manual:** the commands, if you want to run them yourself or see what the agent runs.

Pick a side for each step; you can mix them. `just status` in the project always tells you where you are.

**The agent asks you a question at four points only**, when a step ends, and each message says how to launch what you have and which file to read:
after **step 2** ("Raw disassembly complete: start phase 1?"), after **step 3** ("Named monolith complete: start the phase 2 refactoring?"), after **step 4** ("Refactoring done: review the dead-code list?") and after **step 5** ("Phase 2 complete: play it"). In between it just works, and asks earlier only if it needs something from you.

**Words used below.**
**Reference:** a memory image of the game alone (no loader, no crack); every build is checked against it. **Hand-off:** the moment the game is fully loaded and about to start. **Byte-identical:** the source assembles to exactly the same bytes as the reference. **Slice:** one region of the source worked on in a scratch copy, merged back when its checks pass. **Agent:** the Claude session doing the work, in Claude Code inside the project folder.
**Phase 1** is the named, commented source that is byte-identical to the original. **Phase 2** is the same game split into files, separated from the C64 hardware, and relocatable.

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

## Step 2. Create a source that builds and starts

**Goal:** an `.asm` source that assembles byte for byte to the original game and starts. This is one job in seven parts (research, extracting the files, the clean reference, the Ghidra export, the first build, naming the hardware registers, starting the game; see Appendix A), and there is no point at which you would want to stop in the middle.

| Guided | Manual |
|---|---|
| Open Claude Code in the project folder and say:<br>"Use the MOSaic skill. Do HOWTO step 2: create a source that builds and starts this game, without stopping between its parts."<br><br>The agent tells you each part as it starts and stops early only if it needs something from you: a decision, a missing tool, or a failure it cannot resolve.<br><br>**Do not type in the VICE window** while it dumps memory. A disk takes minutes; a tape longer. | Run the seven parts yourself, in order: **Appendix A**. |

**Done when:** `just smoke` passes and you have seen the game start. The agent then asks whether to start phase 1.

---

## Step 3. Name every routine (phase 1)

**Goal:** every routine named and commented, no raw address operands, no placeholder names, still byte-identical.

| Guided | Manual |
|---|---|
| Say "yes" to the question after step 2, or:<br>"Use the MOSaic skill. Do HOWTO step 3: phase 1, naming every routine. Work in slices, and ask me what a thing is only after trying the code and a tracer run."<br><br>The agent names things from evidence only (the code plus a tracer observation). It **asks you** one question at a time about what a thing is to a player, with a picture, and records each answer in `docs/user_answers.md`. It never asks what the code does. | `just comment-check` (then `comment_check.py --fix` to tidy the export)<br>`just gfx` (sprites and characters into `docs/gfx/`)<br>A slice:<br>`just slice-start NAME`<br>work in `/tmp/mosaic-slices/NAME/project`<br>`just slice-check`<br>`just slice-merge NAME`<br>`just slice-status` shows progress.<br>How much remains:<br>`python3 ~/.claude/skills/mosaic/scripts/p1_complete.py --root . --phase 1` |

**Done when:** the report says `VERDICT: COMPLETE`, `just verify` and `just smoke` pass. Run `git tag p1-byte-identical` and play the game once.

---

## Step 4. Refactor for a port (phase 2)

**Goal:** the named source is split into files, separated from the C64 hardware by a written interface, and proven relocatable, still byte-identical. This is one job in four parts that need nothing from you (the safety net, the split, the interface, relocation; see Appendix B). After this, every command takes the phase: `just verify 2`, `just check 2`, `just launch 2`. Background reading: `references/phase2_split.md` and `references/phase2_port.md`.

| Guided | Manual |
|---|---|
| Say "yes" to the question after step 3, or:<br>"Use the MOSaic skill. Do HOWTO step 4: refactor this game for phase 2, without stopping between its parts, and stop before the removals."<br><br>The agent tells you each part as it starts. | Run the four parts yourself, in order: **Appendix B**. |

**Done when:** `just check 2` passes. The agent then shows you the list of dead blocks and asks you to review it.

---

## Step 5. Remove the dead code

**Goal:** the unused blocks are gone, and the gate proves nothing else changed.

| Guided | Manual |
|---|---|
| Say "yes" to the review question.<br><br>The agent lists every dead block with its size. **You decide which may go**; it records your answer in `docs/user_answers.md`. It removes each approved block leaving a hole, so nothing else moves, and records any bugs of the original it finds (kept, not fixed). | List the removed address ranges in `tools/removals.txt` (one `LO-HI` hex range per line) and set `PHASE2_ALLOWED_DIFF="tools/removals.txt"` in `project.config`. Then:<br>`just verify 2`<br>`just check 2`<br>`just smoke 2`<br>`just launch 2` |

`just verify 2` now passes only when every changed byte is inside the listed ranges.

**Done when:** all four commands pass and **you have played it** with `just launch 2`.

---

## What you have at the end

- `phase1/src`: one commented, byte-identical source (frozen).
- `phase2/src`: the same game in namespaced files with a platform interface, relocation asserts and the dead code removed.
- `docs/`: the research, the boot analysis, your recorded answers, the pictures, the porting contracts, the relocation hazards and the list of removals.
- Commands that always work: `just verify`, `just check`, `just smoke`, `just launch`, `just status`.

**If something goes wrong:** run `just status` and read the evidence it prints. The detailed references are `references/new_game.md` (step 2), `phase1_method.md` (step 3), `phase2_split.md` and `testing.md` (step 4).

---

## Appendix A. The seven parts of step 2

You do not need this unless you are doing step 2 by hand or want to know what the agent is doing. `just status` shows the part you are on.

| Part | What happens | Manual commands | Done when |
|---|---|---|---|
| **2.1 Research** | The manual, release facts, reviews and POKE lists are read and written down as unconfirmed leads. Nothing from the web goes into the code until the code confirms it. | Write `docs/gameplay.md` and `docs/background.md` (method: `references/research.md`; scanned manual: `scripts/research/pdf_pages.py FILE.pdf --out DIR`). | both files are filled in |
| **2.2 Extract and boot chain** | Every file is extracted from the image, the boot stub is disassembled, and what loads what is worked out. A tape with a turbo loader needs a decoder written for that loader. | Disk: `python3 ~/.claude/skills/mosaic/scripts/disk/extract_files.py originals/game.d64 --out extracted/`<br>Tape: `python3 ~/.claude/skills/mosaic/scripts/tape/tap_extract.py originals/game.tap --out extracted/`<br>Then read the stub with `scripts/disasm/dis6502.py` and write `docs/boot_analysis.md`. | `docs/boot_analysis.md` names the boot chain and the hand-off address |
| **2.3 Clean reference** | The game runs in VICE (a scratch copy); RAM is dumped at the hand-off several times, emulator noise is voted out, and loader and crack bytes are zeroed only where the tracer proves the game never touches them. | Set `DUMP_PC`, `HANDOFF_PC` and `REF_KEEP` in `project.config`, list what to zero in `tools/reference.spec`, then `just derive` (its parts: `just dumps`, `just vote`, `just decrunch`, `just reference`). | `reference.sha256` exists |
| **2.4 Ghidra export** | The tracer records which addresses execute; Ghidra follows the code from them and the exporter writes Kick Assembler source. The exporter script downloads itself the first time. | `just seeds`<br>`just ghidra` | `ghidra/<name>.asm` and `ghidra/<name>_Symbols.asm` exist |
| **2.5 First byte-identical build** | The export is copied into `phase1/src/`, the project is pointed at it and the gate is run. | `cp ghidra/<name>.asm phase1/src/<name>.asm`<br>`cp ghidra/<name>_Symbols.asm phase1/src/symbols.asm`<br>Fix the `#import` line at the top to say `symbols.asm`, set `SRC_MAIN="phase1/src/<name>.asm"` in `project.config`, then `just verify` | `just verify` prints `PASS: built image is byte-identical`; from here on it is the gate before every commit |
| **2.6 Name the registers** | Raw register addresses become `VIC.`, `CIA.` and `SID.` names, and short local labels become anonymous. | `just libs-apply`<br>`just verify`<br>`just anon-apply`<br>`just verify` | `just verify` still passes |
| **2.7 Start the game** | The build boots headless in VICE and a screenshot is checked (the first run creates `tools/smoke_ref.png`). | `just smoke`<br>`just launch`<br><br>Some games jam on a fraction of starts; if the original does, keep it and set `SMOKE_RETRIES` in `project.config` (the agent records it in `docs/gameplay.md`). | `just smoke` passes and you have watched the game start |

---

## Appendix B. The four parts of step 4

| Part | What happens | Manual commands | Done when |
|---|---|---|---|
| **4.1 Safety net** | `phase2/src` is created as a copy of `phase1/src`. Routine tests (code run in a simulator against Python models), golden traces (the game's state per frame under scripted input), `docs/platform_layer.md` and `docs/phase2_plan.md` are written. | `rsync -a --exclude build --exclude '*.sym' phase1/src/ phase2/src/`<br>In `project.config`: `PHASE2_MAIN="phase2/src/<name>.asm"` and `ACTIVE_PHASE="2"`.<br>Write tests in `tools/tests/` and scenarios in `tools/golden/`, then `just test 1`, `just golden-record`, `just golden 1` | `just check 1` passes |
| **4.2 Split into files** | Each section moves into its own file under `game/`, `platform/` and `data/`; the gate runs after every move. | Write a plan file (one line per file: `DIR` tab `SECTION` tab `NAME`), then `python3 ~/.claude/skills/mosaic/scripts/split_all.py PLAN`. Cut inside a section: `scripts/cut_section.py`. `just verify 2` after every move. | the phase 2 main file is only imports and `just verify 2` is byte-identical |
| **4.3 Platform interface** | The hardware-facing routines move into namespaces (`Input`, `Time`, `Sound`, `Gfx`, `Storage`, `Boot`) with written contracts. Where a wrapper would cost bytes or cycles in a full image the access is left alone, tagged `TODO(port)`, and the reason written down. | Move the routines into namespaces and write each contract in `docs/porting.md` (inputs, outputs, what is preserved, interrupt safety), then `just check 2` | `docs/porting.md` exists and `just check 2` passes |
| **4.4 Relocatable** | Each relocation hazard is resolved, layout assumptions become `.assert`s, and a layout sweep with a control variant that changes no address proves code can move. Findings go in `docs/relocation_hazards.md`. | `just reloc 2`<br>`just fuzz-layout ...` (options in `references/testing.md`, "Moving the layout"); always include a control variant | every hazard is resolved or documented and the sweep shows no address dependency |
