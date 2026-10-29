# scripts/launcher: start the game, and test that it starts

`run_game.py` starts the assembled game in VICE as the original hand-off did; `smoke.py` does it headless and judges the screenshot. Recipes `launch` and `smoke` in `templates/justfile.in`.

Why no launcher program: the image is RAM ($0800-$FFFF), so there is no room for a BASIC stub at $0801; VICE autostart types RUN, not SYS, so a PRG not at $0801 ends at READY (this is the failure of a project without a launcher); a KERNAL LOAD cannot fill $D000-$DFFF; any launcher code needs free image space and then restoring it. So the launcher is a VICE command line.

- `sys` (default): `x64sc -keybuf "sys <HANDOFF_PC>\r" game.prg` (file last). Proven on a game whose entry initialises its own hardware.
- `inject`: for a game that needs the loader's state: `-initbreak`, then through the text monitor: load the PRG into RAM, write `dumps/handoff.bin` low RAM back, VIC/colour RAM/$DD00 from `dumps/handoff_state.bin` if present, `LAUNCH_POKES`, registers and `$01`, resume at HANDOFF_PC. Starts there with the dump's state.
- `smoke.py`: cheap check (3+ colours, no colour over 97%: fails on READY and on a blank screen) then judge against `JUDGE_REF` (default `tools/smoke_ref.png`, created on the first run: look at it, commit it; `--update-ref`).
Not done: entering at a given raster line, real-hardware/disk image, an NMI-state capture.
