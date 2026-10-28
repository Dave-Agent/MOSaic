# Acquisition and working setup (the user's toolchain)
The full stage-by-stage playbook is `new_game.md`; this page keeps the user's own summary.

From the user, when asked how the projects are done:

1. Find a **non-cracked** version of the game.
2. Load it in **VICE** with a breakpoint at the start of game execution. Some work is needed to find that point and to make sure any decompression has already happened.
3. **Export RAM** from VICE (`dumps/` holds these; `reference/` is the cleaned image derived from them and is immutable).
4. Open it in **Ghidra** and export to Kick Assembler with the plugin https://github.com/Dave-Agent/ghidra-kickass-export (this is the Ghidra export that seeds `phase1/`; from then on the source is hand-edited and Ghidra is downstream).
5. Work through the code with **Claude Code**, supervised in **VS Code**.

Afterwards: source and Ghidra are never edited in both directions at once (`just sync-state`, `just synced <direction>`); `framework/ghidra/import_symbols.py` is the source → Ghidra bridge.

See `new_game.md` for how crack code is told from game code, how the reference image is cleaned and how the first byte-identical build is reached.
