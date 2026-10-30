# HOWTO: from a game's disk or tape file to a finished phase 2

Five steps after setup. Steps 2 and 4 are big jobs that the agent does in the background in several parts; you ask for each once and it tells you the part it is on. The parts are listed in the appendices for anyone who wants the detail.

**How it works.** You tell Claude what to do, or run the setup script, and it does the work. You can always just say **"move to the next stage"**. `just status` in the project tells you where you are.

**The agent asks you a question at four points only**, when a step ends:

- **step 2** ("Raw disassembly complete: start phase 1?")
- **step 3** ("Named monolith complete: start the phase 2 refactoring?")
- **step 4** ("Refactoring done: review the dead-code list?")
- **step 5** ("Phase 2 complete: play it").

**Glossary**

- **Reference:** a memory image of the game alone (no loader, no crack); every build is checked against it. For a game that is a single PRG file, the reference can be that PRG itself, header included (`new_project.py` does this when the medium is a `.prg`, or with `--target prg`): its load address then comes from the PRG's first two bytes, and the third byte of the file is the first byte at that address.
- **Hand-off:** the moment the game is fully loaded and about to start.
- **Byte-identical:** the source assembles to exactly the same bytes as the reference.
- **Slice:** one region of the source worked on in a scratch copy, merged back when its checks pass.
- **Agent:** the Claude session doing the work, in Claude Code inside the project folder.
- **Phase 1** is the named, commented source that is byte-identical to the original.
- **Phase 2** is the same game split into files, separated from the C64 hardware, and relocatable.

---

## Step 0. Set up your machine (once)

**Goal:** the tools are installed and the skill is linked into Claude Code.

First install these. Use your package manager where there is one.

| Tool | For | Where |
|---|---|---|
| Python 3, Java 17+, git, a C compiler | running the scripts, assembling, history, the tracer | your package manager |
| Kick Assembler | assembling | theweb.dk/KickAssembler: put `KickAss.jar` in `~/tools/` |
| `just` | the project's commands | github.com/casey/just |
| VICE (`x64sc`) with its C64 ROMs | running the game, memory dumps | your package manager |
| Ghidra 11+ | the first disassembly | ghidra-sre.org: unzip in your home folder. Ghidra 11 needs Java 17+. Ghidra 12 needs JDK 25, and once you run `support/pyghidraRun -H` and answer `y` to set up PyGhidra |
| Claude Code | the agent you talk to | claude.com/claude-code |

```
git clone https://github.com/Dave-Agent/MOSaic.git ~/MOSaic
cd ~/MOSaic
claude
```

Then say **"Set up MOSaic for me."** Claude links the skill, checks the tools and tells you how to get any that are missing, then does step 1 with you. It installs nothing without your yes. (`./setup.sh` does the same from a terminal; `./setup.sh --check` only checks the tools.)

**Done when:** the check ends with `all required tools present`.

---

## Step 1. Add the game

**Goal:** a project folder holding your copy of the game's disk or tape file (`.d64`, `.g64` or `.tap`; a copy with the copy protection removed is best).

Claude asks for it as the last part of the setup: the path of the game file, its name, and the project folder (it suggests one). Then it tells you the line to open Claude Code in the project, for example `cd ~/C64Projects/my-game && claude`, where you say "move to the next stage". If you set up with `./setup.sh` instead, it asks the same three things.

Your file is copied into the project's `originals/` folder and its SHA-256 recorded. The original is never modified and never loaded into an emulator directly; VICE only runs temporary copies.

**Done when:** `just status` says `NEXT: step 2.1`.

---

## Step 2. Create a source that builds and starts

**Goal:** an `.asm` source that assembles byte for byte to the original game and starts. This is one job in seven parts (research, extracting the files, the clean reference, the Ghidra export, the first build, naming the hardware registers, starting the game; see Appendix A).

Open Claude Code in the project folder and say **"move to the next stage"**, or, to be explicit:

> Use the MOSaic skill. Create a source that builds and starts this game, without stopping between its parts.

The agent tells you each part as it starts and stops early only if it needs something from you: a decision, a missing tool, or a failure it cannot resolve.

**Do not type in the VICE window** while it dumps memory. A disk takes minutes; a tape longer.

**Done when:** `just smoke` passes and you have seen the game start. The agent then asks whether to start phase 1.

---

## Step 3. Name every routine (phase 1)

**Goal:** every routine named and commented, no raw address operands, no placeholder names, still builds byte-identical to the original.

Say "yes" to the question after step 2, or:

> Use the MOSaic skill. Do phase 1: name every routine. Work in slices, and ask me what a thing is only after trying the code and a tracer run.

The agent names things from evidence only (the code plus a tracer observation). It **asks you** one question at a time about what a thing is to a player, with a picture, and records each answer in `docs/user_answers.md`. It never asks what the code does.

To see how far it is, run `just gauge` in the project: a bar for each area of the source showing how much is still raw addresses or unnamed, and an overall figure (`just status` quotes the last reading). It counts references, not routines, so treat it as an estimate that moves the right way.

**Done when:** the report says `VERDICT: COMPLETE`, `just verify` and `just smoke` pass. Run `git tag p1-byte-identical` and play the game once.

---

## Step 4. Refactor ready for future development (phase 2)

**Goal:** the named source is split into files, separated from the C64 hardware by a written interface, and proven relocatable, still byte-identical. This is one job in four parts that need nothing from you (the safety net, the split, the interface, relocation; see Appendix B). After this, every command takes the phase: `just verify 2`, `just check 2`, `just launch 2`. Background reading: `references/phase2_split.md` and `references/phase2_port.md`.

Say "yes" to the question after step 3, or:

> Use the MOSaic skill. Refactor this game for phase 2, without stopping between its parts, and stop before the removals.

The agent tells you each part as it starts.

**Done when:** `just check 2` passes. The agent then shows you the list of dead blocks and asks you to review it.

---

## Step 5. Remove the dead code

**Goal:** the unused blocks are gone, and the gate proves nothing else changed.

Say "yes" to the review question.

The agent lists every dead block with its size. **You decide which may go**; it records your answer in `docs/user_answers.md` and the list of removals in `docs/phase2_removals.md`. It removes each approved block leaving a hole, so nothing else moves, and records any bugs of the original it finds (kept, not fixed).

`just verify 2` then passes only when every changed byte is inside the removed ranges.

**Done when:** `just verify 2`, `just check 2` and `just smoke 2` pass and **you have played it** with `just launch 2`.

---

## What you have at the end

- `phase1/src`: one commented, byte-identical source (frozen).
- `phase2/src`: the same game in namespaced files with a platform interface, relocation asserts and the dead code removed.
- `docs/`: the research, the boot analysis, your recorded answers, the pictures, the porting contracts, the relocation hazards and the list of removals.
- Commands that always work: `just verify`, `just check`, `just smoke`, `just launch`, `just status`.

**If something goes wrong:** run `just status` and read the evidence it prints. The detailed references are `references/new_game.md` (step 2), `phase1_method.md` (step 3), `phase2_split.md` and `testing.md` (step 4).

---

## Appendix A. The seven parts of step 2

You do not need this unless you want to know what the agent is doing. `just status` shows the part you are on.

| Part | What happens | Done when |
|---|---|---|
| **2.1 Research** | The manual, release facts, reviews and POKE lists are read and written down as unconfirmed leads. Nothing from the web goes into the code until the code confirms it. | both files are filled in |
| **2.2 Extract and boot chain** | Every file is extracted from the image, the boot stub is disassembled, and what loads what is worked out. A tape with a turbo loader needs a decoder written for that loader. | `docs/boot_analysis.md` names the boot chain and the hand-off address |
| **2.3 Clean reference** | The game runs in VICE (a scratch copy); RAM is dumped at the hand-off several times, emulator noise is voted out, and loader and crack bytes are zeroed only where the tracer proves the game never touches them. For a PRG target, `just reference` simply copies the PRG from `originals/` and records its SHA-256; nothing is zeroed. | `reference.sha256` exists |
| **2.4 Ghidra export** | The tracer records which addresses execute; Ghidra follows the code from them and the exporter writes Kick Assembler source. The exporter script downloads itself the first time. | `ghidra/<name>.asm` and `ghidra/<name>_Symbols.asm` exist |
| **2.5 First byte-identical build** | The export is copied into `phase1/src/`, the project is pointed at it and the gate is run. | `just verify` prints `PASS: built image is byte-identical`; from here on it is the gate before every commit |
| **2.6 Name the registers** | Raw register addresses become `VIC.`, `CIA.` and `SID.` names, and short local labels become anonymous. | `just verify` still passes |
| **2.7 Start the game** | The build boots headless in VICE and a screenshot is checked (the first run creates `tools/smoke_ref.png`). | `just smoke` passes and you have watched the game start |

---

## Appendix B. The four parts of step 4

| Part | What happens | Done when |
|---|---|---|
| **4.1 Safety net** | `phase2/src` is created as a copy of `phase1/src`. Routine tests (code run in a simulator against Python models), golden traces (the game's state per frame under scripted input), `docs/platform_layer.md` and `docs/phase2_plan.md` are written. | `just check 1` passes |
| **4.2 Split into files** | Each section moves into its own file under `game/`, `platform/` and `data/`; the gate runs after every move. | the phase 2 main file is only imports and `just verify 2` is byte-identical |
| **4.3 Platform interface** | The hardware-facing routines move into namespaces (`Input`, `Time`, `Sound`, `Gfx`, `Storage`, `Boot`) with written contracts. Where a wrapper would cost bytes or cycles in a full image the access is left alone, tagged `TODO(port)`, and the reason written down. | `docs/porting.md` exists and `just check 2` passes |
| **4.4 Relocatable** | Each relocation hazard is resolved, layout assumptions become `.assert`s, and a layout sweep with a control variant that changes no address proves code can move. Findings go in `docs/relocation_hazards.md`. | every hazard is resolved or documented and the sweep shows no address dependency |
