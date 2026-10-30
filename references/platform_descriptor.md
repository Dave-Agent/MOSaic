# Platforms as data (issue #39)

**Status: defined, not yet read.** `platforms/c64/platform.json` says what the tools assume about the C64 today; `scripts/platform.py` loads, validates and queries it. No tool reads it yet: moving them over is the work of the next phases. Scope: 6502-family machines only (#38 is the assembler question).

## What a platform is
A platform is not one file. It is five things, and the descriptor holds the data and names the rest:

| Part | What it is | The C64's |
|---|---|---|
| **Descriptor** | the data: CPU, memory map and banking, chips and their registers, video, input, boot, media, emulator, the noise in a dump | `platforms/c64/platform.json` |
| **Register libraries** | the names of the registers, one file per chip | `libs/vic.asm`, `sid.asm`, `cia.asm`, `cpu.asm` (a platform may bring its own in `platforms/<id>/libs/`) |
| **Machine model** | the code that runs a game far enough to record what executes | `scripts/trace/c64trace.c` |
| **Emulator adapter** | start the real emulator unattended, reach its monitor, take a screenshot | VICE: `scripts/vice`, `scripts/launcher` |
| **Media adapters** | read the medium the game came on | disk, tape, PRG: `scripts/disk`, `scripts/tape` |

A project names its platform in `project.config` (`PLATFORM="c64"`); without the key it is the c64, so no existing project changes.

## The descriptor, section by section
Addresses are hex strings without a prefix. Every section has a `used_by` list: the code that will read it (a self-test checks the files exist, so the map cannot drift).

| Section | Holds | Replaces an assumption in |
|---|---|---|
| `cpu` | the variant, the Kick `.cpu` name, decimal mode, the on-chip I/O port, the three vectors | tracer, simulator, `apply_libs.py`, entry points |
| `memory.regions` | the CPU's view as regions (`ram`, `rom`, `io`) that tile the address space, with what lies under a ROM | `raw_refs.py`, the tracer, the renderer |
| `memory.banking` | the banking register, its bits, and a rule per region (`when: "(LORAM or HIRAM) and CHAREN"`) | the tracer's memory map |
| `memory.rom_images` | the ROM files the model needs | `check_env.py`, `rom_dir.py`, the tracer |
| `chips` | each chip: its block, its mirror step, its register range, its library and scope | `apply_libs.py`, `platform_deps.py` |
| `video` | the standard's raster geometry, text and sprite geometry, the banks and the register that picks one, the palette | `gfx_sheets.py`, `screen_regions.py`, the tracer |
| `input` | joysticks, the keyboard matrix and how it is read | the tracer |
| `boot` | the load address, whether a BASIC stub starts it, the hand-off, a cartridge's cold start | launcher, `vice_handoff.py`, `new_project.py` |
| `media` | the medium types, the PRG header, the tool for each | the extraction scripts, `check_env.py` |
| `emulator` | the emulator and the flags for an unattended run | `scripts/vice`, `scripts/launcher` |
| `dump_noise` | the bytes of a RAM dump that are machine state and differ between dumps (the jiffy clock at `$A2`, the cursor timers, stack leftovers) | `golden.py variance` / `GOLDEN_PIN` |
| `hardware_markers` | the KERNAL jump table, the raster register, the interrupt flags: what a port has to replace | `port_scan.py`, `platform_deps.py`, `reloc_hazards.py` |
| `tracer` | the model's file and its start defaults | the tracer's callers |

`platform.py visible c64 D000 05` answers "what does the CPU see at `$D000` when `$01` is `$05`?" from the banking rules; a self-test compares that with the tracer's own memory map for every value of `$01`, so the data and the code that will be replaced agree today.

## Phases
1. **Define (done on this branch).** The C64 as data, the loader and validator, tests that tie the data to the code it will replace, this page.
2. **Read-only consumers.** Move the tools that only look things up onto the descriptor, one at a time: the mirror and vector tables of `apply_libs.py`, `port_scan.py` and `platform_deps.py`, the I/O exclusion of `raw_refs.py`, the ROM names of `check_env.py`, the dump-noise defaults of `golden.py`. Each swap must change no output on the existing projects (the byte-identical gate, the self-tests, a replay of a real project).
3. **The machine model.** Split `c64trace.c` into a CPU core and a machine file so another machine can be added without touching the core; the machine reads its parameters from the descriptor.
4. **Emulator and media adapters.** A small interface (start unattended, monitor, screenshot, scratch copy of the medium) with VICE as the first implementation; the media tools selected by `media.types`.
5. **A second platform.** The NES as the second instance: a descriptor, a machine model, an emulator adapter (a headless Mesen test already exists in a prototype), a renderer for the PPU.
6. **A byte-identical NES project** as the proof.

## Open design questions
- **The reference image.** The gate compares one flat image. A NES cartridge is a header and banked ROM: the descriptor needs a `layout` (flat or banked, bank size, mapper) and the gate a way to compare banks. This is the real test of the format.
- **Hand-off.** A cartridge starts at the reset vector with no loader and no BASIC stub; `boot` has to say so, and `new_project.py` and the HOWTO steps that talk about hand-off have to follow.
- **The model's interface.** Table-driven (the descriptor describes the chips) or code (one machine file each)? The chips' behaviour is code; the descriptor can only give parameters.
- **The renderer.** `gfx_sheets.py` is a VIC-II renderer; the PPU has a different model (pattern tables, nametables, OAM).
- **Dialect.** Which assembler a platform uses is #38; the descriptor's `cpu.assembler` names the setting for Kick today.

## Rules for a descriptor
- No game data, no game names: a platform is a machine.
- A value is what a tool assumes or what the hardware says, with its reader named in `used_by`; a field no tool will read does not belong.
- Facts the descriptor and the code both hold are tied by a self-test, so one cannot change without the other (a descriptor that disagrees with the machine model is a bug).
