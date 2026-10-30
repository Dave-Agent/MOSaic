# MOSaic: setting up for a new user

This folder is the MOSaic skill. When the user opens Claude Code here and asks to set up, get started or add a game, do the setup for them in this conversation. Ask the questions yourself, one at a time, in plain words; do not tell them to run `./setup.sh` and answer its prompts.

1. **Link and check.** Run `./setup.sh --link`. It links this folder as `~/.claude/skills/mosaic` (never replacing something that is already there) and checks the tools. If it reports a tool as MISSING, tell the user what it is for and how to get it (the output says), offer to run the install command if it is a package-manager one, and run `./setup.sh --link` again. Install nothing without their yes. Kick Assembler and Ghidra are downloads: say where, and where to put them.
2. **Ask for the game.** The path of the game's disk or tape file (`.d64`, `.g64` or `.tap`; a copy with the copy protection removed is best), then its name (offer one made from the file name), then the project folder (offer `~/C64Projects/<name-in-lower-case-with-dashes>`). Check the file exists.
3. **Create the project.** Run `./setup.sh --root FOLDER --name "NAME" --media FILE`. It copies the file into the project; the original is never touched.
4. **Say what to do next, with the real folder in it:** open a new Claude Code session in the project folder (`cd FOLDER && claude`) and say "move to the next stage". That session loads the project's own instructions; this one does not. Then stop: do not start step 2 from here.

The step-by-step is `HOWTO.md`. Everything about how to work on a game is in `SKILL.md`, which loads once the skill is linked.
