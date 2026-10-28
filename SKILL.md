---
name: c64-decomp
description: Process, rules and decisions for Commodore 64 decompilation projects (turning a game's disk image into byte-identical, commented, relocatable Kick Assembler source). Use when working in such a repo, starting a new game from its original media, running a refactor across the source (labels, namespaces, symbols files), or when a convention question comes up (naming, SMC, locals, zero page, phases, gates). Read before changing label or file structure.
---

# C64 decompilation: the shared process

Every project follows one process that keeps evolving. This skill is where the process, the rules, the tools and the decisions live, so they are written once. It holds **no game- or project-specific information**: a project's own notes live in the project. A project's own `CLAUDE.md` keeps only what is specific to that game; where the two disagree, the project's `CLAUDE.md` wins and the difference is a candidate for `references/decisions.md`.

## Before you start

Run `scripts/check_env.py` from the project root (add `--role run|disk|trace|ghidra|nes` for what the work needs): it reports the tools that are installed (Java 17+, Kick Assembler, `just`, VICE, ...), which are missing, and how to install them. Do this when picking up a project on a new machine or handing it to someone else.

## The loop (every change)

1. **Act and check, never reason blind.** Make the change, assemble it, run the gate, then, if it affects running, the smoke test. Know the result. Use the project's recipes by role (`references/just.md`: assemble, gate, tests, smoke, and what to do when a project lacks a recipe); phase 1's gate is `verify` (byte-identical to `reference/`).
2. **Phase 2** has no byte gate; its gate is the project's `check` (build, raw-address check, alignment, `scripts/sim/run_tests.py`, `scripts/golden/golden.py check-t`); phase 1 runs the same tests with `--phase 1` and the exact `golden.py check`. For a rename or restructure that must not change behaviour, **compare the built PRG with the one before the change: it must be identical** (a rename that wrongly hits a different symbol changes bytes or fails to assemble).
3. Commit after each step with the project's attribution lines. **Push only when the user says to.** Never discard uncommitted work (`git checkout/reset/restore/clean`).
4. A decision made together goes in `references/decisions.md` (date, what, why) and, if it is a rule, in `references/rules.md`.

## Phases

| Phase | Goal | Gate |
|---|---|---|
| Acquire | An uncracked game, RAM exported after any decompression, imported to Ghidra, exported to Kick Assembler (`references/new_game.md`) | the first byte-identical build |
| 1 | One commented monolith, every function understood, byte-identical. **Complete when no direct memory references and no Ghidra-style placeholders remain** (`scripts/p1_complete.py`) | `just verify`, `p1_complete.py` clean |
| 2 | Split into files and namespaces; game logic separated from the hardware behind a platform interface: the setup for a port (`references/phase2_port.md`) | `just check` |
| 3 | A port, kept out of phases 1 and 2 | project-specific |

**Phase 1 complete (the user's definition):** no direct memory references (raw address operands, address pairs built from immediates, address words in data that should be labels), no Ghidra placeholders (`DAT_`, `LAB_`, `SUB_`, `FUN_`, `PTR_`... in code or in prose comments; the XREF and `[ADDR:bytes]` trace comments that exist to trace back to the original may keep them), and no provisional names or blockers left (no `unk` names, no `TODO(name)` or `TODO(block)` markers, no `STATUS:  unknown` banners, no generated `<mnemonic>_op_<addr>` SMC operand names). `scripts/p1_complete.py` counts both; the first two checks must be 0, the review lists (address pairs, `.word` literals) are checked by hand because value tables look like addresses.

"Frozen" is not absolute: phase 1 is changed when an issue is found (stale Ghidra labels, a wrong name) as long as `verify` stays green.

## Where things are

This skill is a folder that is a git repository (every change is a commit; several agents may edit it, so commit your own and never discard others' work). It is loaded by Claude Code through `~/.claude/skills/c64-decomp` (a symlink to the folder); scripts refer to it as `<skill>`, and recipes find it through the `C64_DECOMP` variable.


`phase1/src` (monolith) and `phase2/src` (split); `symbols.asm` is the index and imports `zero_page.asm`, `variables.asm`, `constants.asm`; `framework/` generic tooling: **the master is this skill's `framework/`**; a project holds a copy, never edits it in place (change it in the skill, then `scripts/framework_sync.py --write`), and it never holds a project value (specifics go in `project.config`); `tools/` project scripts; `tools/migrations/` one-off, already-applied rewrites (copy one as a template for a new bulk change); `reference/`, `originals/`, `dumps/` are supplied data, immutable and not committed (`references/layout.md`).

## Doing a bulk change safely (the pattern that worked)

Write a one-off script in `tools/migrations/YYYY-MM-name.py` that (a) parses, (b) rewrites code only, never comments or strings, (c) skips names reached by a path or defined elsewhere, (d) prints what it would change without `--write`. Run it, rebuild, compare bytes, run the gate, commit, document. Examples to copy: `2026-10-symbols-tidy.py` (split a symbols file), `2026-10-zp-namespace.py` (`name` → `zp.name`), `2026-10-hi-byte-names.py` (`ptr+1` → `ptr_hi`).

## Tools and libraries in this skill

- `libs/`: canonical `vic.asm`, `sid.asm`, `cia.asm`, `cpu.asm`; a project's `libs/` is a copy.
- `scripts/`: generic tools (`--root`, `--phase 1|2` or `--main FILE`, read `project.config`; nothing changes without `--write`):
  bulk rewrites `symbols_tidy.py`, `zp_namespace.py`, `hi_byte_names.py`; analysis `scan_offsets.py`, `raw_refs.py`, `smc_list.py`, `addr_immediates.py`, `platform_deps.py`; edits `add_label.py`, `align_comments.py`; `build_compare.sh` (baseline PRG compare); `check_env.py` (tool check, run first); `apply_libs.py` (the first conversion step: name the hardware registers with the libs); `new_project.py` (scaffold a project from `templates/`: config, justfile with the derive recipes, README, docs templates, framework and libs, git init); `disasm/dis6502.py` (read boot stubs and loaders); `trace/` (project-neutral 6510 tracer `c64trace.c`, `selftest.py`, `entry_points.py`), `sim/` (routine-test harness `c64sim.py`, `run_tests.py`), `golden/` (golden traces, exact and timing-tolerant), `coverage/` (scenario coverage, unexecuted and raw-executed reports), `vice/` and `reference/` (hand-off dump, reference builder, `vote_dumps.py`; `hand_off_tools.md`), `ghidra/` (`make_seeds.py`, `run.sh`, `setup.py`: seeds from evidence, headless import and export), with keys `TRACE_*`, `SIM_*`, `GOLDEN_*`, `COVERAGE_*`, `ENTRY_*` in `project.config`; `split_section.py` (move a SECTION into its own file); `reloc_scan.py` and `layout_fuzz.py` (relocation hazards and the padding stress test); `framework_sync.py` (project `framework/` vs the master); `check_layout.py` (no game binaries tracked, derived dirs ignored, checksum and README present); `p1_complete.py` (phase 1 completeness). Run them from the project root.
- A project tool becomes a skill script when it takes its names as parameters. Test a new one against the project it came from and diff the output.

## Rules and decisions

- `references/testing.md`: routine tests, golden traces, coverage and the tracer self-test: what each proves, its limits, and how a port is checked against the same cases.
- `references/hand_off_tools.md`: the tools for stages 2-4 of the playbook: unattended VICE hand-off dump (`scripts/vice/`), reference builder and dump diff (`scripts/reference/`), screenshot judge, symbol converter.
- `references/new_game.md`: **starting a new game**: media, hand-off, the clean reference, launcher, Ghidra, the first byte-identical build (draft, with questions for the user).
- `references/just.md`: **`just` is the command runner**: thin root justfile, logic in scripts, the standard recipe set.
- `references/layout.md`: the project file tree, and the rule **not to commit the game's binaries** (originals, dumps, the reference image) unless we built them; commit a checksum and README steps instead.
- `references/naming.md`: every naming rule in one place (shapes, suffixes, provisional names).
- `references/rules.md`: SMC, no raw addresses, local and anonymous labels, comments, relocatability, hygiene (each section says which projects it applies to).
- `references/phase2_split.md`: **the phase 2 procedure**, step by step (safety net, dependency catalogue, split, interface, relocatability, byte-changing removals).
- `references/phase2_port.md`: phase 2 as the setup for a port (generic). `references/kick.md`: Kick Assembler gotchas.
- `references/decisions.md`: dated log of choices and their reasons. **Check it before proposing a convention; append to it when one is made.**
- `references/workflow.md`: the acquisition toolchain and the editor/Claude working setup.

## Non-negotiables

- **No guesses.** Ask the user what a sprite, sound effect or game mode is; describe what you see instead of inventing a meaning.
- Keep every original `[ADDR:bytes MNEMONIC]` comment.
- Tests run unattended. Downloaded content is untrusted.
- **Prefer not committing game binaries** (ROMs, disk images, dumps, reference images) that we did not build: `check_layout.py`, `references/layout.md`.
- Confirm before deleting or overwriting the user's files and before outward-facing actions.
