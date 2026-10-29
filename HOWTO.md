# HOWTO: from a game image to a finished phase 2

Step 0 sets up your machine (once). Then fourteen steps. Each one says what you tell Claude, what the agent does, and how you know it is done. At any point, `just status` in the project names the step you are on, and saying **"move to the next stage"** to Claude does the next one.

**What "phase 1" and "phase 2" mean.** Phase 1 turns the game into one fully commented source file that assembles to exactly the original bytes. Phase 2 splits that source into files, separates the game from the C64 hardware, and makes it relocatable. Phase 1 is frozen once finished (git tag `p1-byte-identical`); phase 2 is a separate copy.

**Words used below.**
- **Image:** the game's disk or tape file.
- **Reference:** a memory image of the game alone, with no loader or crack, made in step 4. Every build is checked against it.
- **Hand-off:** the moment the game is fully loaded in memory and about to start.
- **Byte-identical:** the source assembles to exactly the same bytes as the reference.
- **Slice:** one region of the source worked on in a scratch copy and merged back when its checks pass.
- **Agent:** the Claude session doing the work. You talk to it in Claude Code, inside the project folder.

---

## Step 0: set up your machine (once)

**1. Install these tools.** Use your system's package manager where there is one.

| Tool | What it is for | Where to get it |
|---|---|---|
| Python 3 | runs the skill's scripts | your package manager |
| Java 17 or newer | runs Kick Assembler | your package manager |
| Kick Assembler | assembles the source | download from theweb.dk/KickAssembler and put `KickAss.jar` in `~/tools/` |
| git | keeps the history | your package manager |
| `just` | runs the project's commands | github.com/casey/just |
| VICE (`x64sc`) with its C64 ROM files | runs the game and takes memory dumps | your package manager, or vice-emu.sourceforge.io |
| Ghidra 11 or newer | the first disassembly | ghidra-sre.org: unzip it in your home folder (or set `GHIDRA_HOME`) |
| a C compiler (`gcc` or `clang`) | builds the skill's tracer | your package manager |
| Claude Code | the agent you talk to | claude.com/claude-code |

The Ghidra exporter script downloads itself the first time it is needed.

**2. Get the skill, and link it so Claude Code can find it.**
```
git clone https://github.com/Dave-Agent/MOSaic.git ~/MOSaic
mkdir -p ~/.claude/skills
ln -s ~/MOSaic ~/.claude/skills/c64-decomp
```
The link must be called `c64-decomp`: that is the name the skill is registered under, and the commands in this guide use that path.

**3. Check the tools.**
```
python3 ~/.claude/skills/c64-decomp/scripts/check_env.py --role run --role trace --role ghidra
```
The last line should read `all required tools present for roles: build, ghidra, run, trace`. If it lists missing tools, install them and run it again.

**Done when:** that last line says all required tools are present.

---

## Steps 1 to 8: from the image to a game that builds and starts

### 1. Add the game
**What you need:** the game's disk or tape file. It ends in `.d64`, `.g64` or `.tap`. A copy with the copy protection removed is best.

**Do this once, in a terminal:**

1. **Choose a folder for the project.** It can be new or empty. Example: `~/C64Projects/MyGame`.
2. **Run this command.** Change the three parts after `--root`, `--name` and `--media`:
   ```
   python3 ~/.claude/skills/c64-decomp/scripts/new_project.py \
     --root ~/C64Projects/MyGame \
     --name "My Game" \
     --media ~/Downloads/mygame.d64
   ```
   - `--root` is the project folder from step 1.
   - `--name` is the game's name.
   - `--media` is the path to the disk or tape file.
3. **Go into the folder and check your tools:**
   ```
   cd ~/C64Projects/MyGame
   just env
   ```
   You should see a list of tools, each marked `ok`. If one says `absent`, install it as the message says, then run `just env` again.
4. **Check where you are:**
   ```
   just status
   ```
   The first two lines should say `done  step 1`, and below them `NEXT: step 2`.

**What just happened:** a project folder was created. Your game file was copied into its `originals/` folder (your own copy elsewhere is untouched), its SHA-256 fingerprint was saved in `originals.sha256`, and a git repository was started. From now on the original is never changed, and is never loaded into an emulator directly: VICE only ever runs a temporary copy.

Optional: add `--protect` to the command to make the copy in `originals/` read-only.

**Done when:** `just env` shows no `absent` tools and `just status` says `NEXT: step 2`.

### 2. Research the game
**You say:** "Use the MOSaic skill. Research this game before reading any code."
**The agent:** reads the manual, release databases, wikis, reviews and POKE lists, and writes `docs/gameplay.md` (one row per documented fact, marked unconfirmed) and `docs/background.md`. Nothing from the web goes into the code until the code confirms it.
**Done when:** both files are filled in.

### 3. Extract the files and work out the boot chain
**The agent:** extracts every file (disk: `scripts/disk/extract_files.py`; tape: `scripts/tape/tap_extract.py`), disassembles the boot stub, and works out what loads what, up to the jump into the game. It writes `docs/boot_analysis.md`. A tape with a turbo loader needs a decoder written for that loader, or the memory dump route in step 4.
**Done when:** `docs/boot_analysis.md` names the boot chain and the address where the game starts (the *hand-off*).

### 4. Derive the clean reference
**Goal:** a memory image of the game alone: no loader, no crack, no intro.
**The agent:** sets `DUMP_PC`, `HANDOFF_PC` and `REF_KEEP` in `project.config`, then runs `just derive`. That runs VICE on a scratch copy, dumps RAM at the hand-off several times, votes out emulator noise (`just vote`), and writes `reference/` with its SHA-256 in `reference.sha256`. Loader and crack bytes are zeroed only where the tracer proves the game never touches them (`tools/reference.spec`).
**Do yourself:** don't type in the VICE window while it runs. A disk takes minutes; a tape longer.
**Done when:** `reference.sha256` exists and `docs/` explains where the reference came from.

### 5. Export the disassembly from Ghidra
**The agent:** runs `just seeds` (the tracer runs the game and records which addresses execute) and then `just ghidra` (Ghidra follows the code from those addresses and the exporter writes Kick Assembler source). The exporter script downloads itself on first use. The result lands in `ghidra/`, which is a landing zone and not yet your source.
**Done when:** `ghidra/<name>.asm` and `ghidra/<name>_Symbols.asm` exist.

### 6. Get the first byte-identical build
**The agent:** copies the export into `phase1/src/` as the main file and `symbols.asm`, fixes the `#import` line, sets `SRC_MAIN` in `project.config`, and runs `just verify`. The goal is `PASS: built image is byte-identical to the reference`. If it fails, `references/new_game.md` lists the usual first differences.
**Done when:** `just verify` passes. From here on it is the gate: it must pass before every commit.

### 7. Name the hardware registers
**The agent:** runs `just libs-apply` (raw register addresses become `VIC.`, `CIA.` and `SID.` names) and then `just anon-apply` (short local labels become anonymous). It runs `just verify` after each.
**Done when:** `just verify` still passes and `just status` shows this step done.

### 8. Start the game
**The agent:** runs `just smoke` (VICE boots the build headless and takes a screenshot; the first run creates `tools/smoke_ref.png`) and looks at the picture to confirm it is the game, not a blank or BASIC screen. Then try `just launch` yourself: it starts the game in VICE with symbols.
**Note:** some games jam on a fraction of starts. If the original does, that is a bug of the original and is kept; set `SMOKE_RETRIES` so `just smoke` retries, and the agent records it in `docs/gameplay.md`.
**Done when:** `just smoke` passes and you have seen the game start.

---

## Step 9: phase 1, understand every routine

**Goal:** every routine named and commented, no raw address operands, no placeholder names, still byte-identical.
**You say:** "Start phase 1 following `references/phase1_method.md`. Work in slices, and ask me what a thing is only after trying the code and a tracer run."
**The agent:**
- tidies the exporter's output first (`just comment-check`, then `comment_check.py --fix`; `just gfx` renders the sprites and characters into `docs/gfx/`);
- works in **slices**: `just slice-start NAME` makes a scratch copy, the agent names and comments one region there, `just slice-check` must pass, then `just slice-merge NAME` takes the commits into the project. `just slice-status` shows progress while a slice runs;
- names things from evidence only: the code plus an observation from a tracer run (`just trace-run`). A name that claims a role needs both;
- **asks you** one question at a time about what a thing is to a player (what a sprite, sound or mode is), with a picture, and records each answer in `docs/user_answers.md`. It never asks what the code does.
**Check progress:** `python3 ~/.claude/skills/c64-decomp/scripts/p1_complete.py --root . --phase 1` lists what remains.
**Done when:** that report says `VERDICT: COMPLETE`, `just verify` passes and `just smoke` passes. Tag it: `git tag p1-byte-identical`. Play the game once.

---

## Steps 10 to 14: phase 2, a source ready for a port

Phase 2 works on a copy: `rsync -a --exclude build --exclude '*.sym' phase1/src/ phase2/src/`, with `PHASE2_MAIN` set in `project.config` and `ACTIVE_PHASE="2"`. Every command now takes the phase: `just verify 2`, `just check 2`, `just launch 2`. Read `references/phase2_split.md` and `references/phase2_port.md` first.

### 10. Build the safety net
**You say:** "Start phase 2 step 1 and 2: the safety net and the hardware catalogue."
**The agent:** writes routine tests (`tools/tests/`, code run in the simulator against Python models), golden traces (`tools/golden/`: the game's state per frame under scripted input that starts the game), `docs/platform_layer.md` (which routines touch hardware) and `docs/phase2_plan.md`. Then `just test 1` and `just golden 1` must pass.
**Done when:** `just check 1` passes.

### 11. Split the source into files (still byte-identical)
**The agent:** moves each section into its own file under `game/`, `platform/` and `data/` with `scripts/split_all.py` and `scripts/cut_section.py`, running `just verify 2` after every move.
**Done when:** the phase 2 main file is only imports and `just verify 2` is byte-identical.

### 12. Define the platform interface
**The agent:** puts the hardware-facing routines in namespaces (`Input`, `Time`, `Sound`, `Gfx`, `Storage`, `Boot`) with written contracts in `docs/porting.md`. Where a wrapper would cost bytes or cycles in a full image, it leaves the access alone, tags it `TODO(port)` and says why. Byte-identical throughout.
**Done when:** `docs/porting.md` exists and `just check 2` passes.

### 13. Make it relocatable
**The agent:** runs `just reloc 2`, resolves each item (an anchored hardware address, an address that must become a label, or a plain number), turns layout assumptions into `.assert`s, and runs the layout sweep (`just fuzz-layout` with a control variant that changes no address) to prove that code can move. Findings go in `docs/relocation_hazards.md`.
**Done when:** the hazards are resolved or documented and the sweep shows no address dependency.

### 14. Remove the dead code
**You decide:** the agent lists every dead block with its size. Which may go is the owner's decision; it records your answer in `docs/user_answers.md`.
**The agent:** removes each approved block *without moving anything else* (leaving a hole), lists the changed address ranges in `tools/removals.txt` (`PHASE2_ALLOWED_DIFF` in `project.config`), and `just verify 2` then passes only when every changed byte is inside those ranges. It also moves any data that lives in the code stream to a real variable and records the original's bugs (kept, tagged `TODO(phase2): original bug`).
**Done when:** `just verify 2`, `just check 2`, `just smoke 2` pass and **you have played it** with `just launch 2`.

---

## What you have at the end
- `phase1/src`: one commented, byte-identical source (frozen).
- `phase2/src`: the same game in namespaced files with a platform interface, relocation asserts and the dead code removed.
- `docs/`: research, boot analysis, your recorded answers, the pictures, the porting contracts, the relocation hazards and the list of removals.
- Commands that always work: `just verify`, `just check`, `just smoke`, `just launch`, `just status`.

**If something goes wrong:** run `just status` and read the evidence it prints. The detailed references are `references/new_game.md` (steps 1 to 8), `phase1_method.md` (step 9), `phase2_split.md` and `testing.md` (steps 10 to 14).
