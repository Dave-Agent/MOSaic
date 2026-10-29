# `just` is the command runner (all three projects use it)

**Prefer `just` over Makefiles, shell aliases or remembered command lines.** One entry point per project: `just` with no arguments lists every recipe with its one-line description, so a person or an agent finds the gate, the build and the checks without reading docs.

## Conventions (from the three justfiles)
- **The root `justfile` is thin.** It imports `framework/recipes.just` (generic recipes, no project values, never edited in a project) and adds or overrides project recipes. `set allow-duplicate-recipes := true` lets a project override an imported recipe of the same name (for example `launch`, `smoke`).
- **Logic lives in scripts, not in the justfile.** A recipe is a one-line call to `framework/scripts/*.sh`, `tools/*.py` or a skill script; anything with a loop or a condition goes in a script that can be tested and read. Longer recipes use a `#!/usr/bin/env bash` shebang and `set -euo pipefail`.
- **Project specifics come from `project.config`** (sourced by the scripts), never hard-coded in a recipe. `PROJECT_ROOT` is exported so scripts work from any directory.
- **Every recipe has a comment line above it**: that is what `just --list` shows. Say what it does and how long it takes if it is slow.
- **Recipes run unattended** (no prompts, no GUI waits); anything that needs an emulator window is a separate, clearly named recipe (`launch`, `debug-*`).
- **Machine-local recipes go in `local.just`** (not tracked): ones that need supplied data (`originals/`, `reference/`) or tools not everyone has.
- **Arguments with `$`** are expanded by the shell: do not pass hex through a recipe argument; use a script argument file instead.
- **A recipe prints its result and exits non-zero on failure**, so `just check && git commit` works.

## Calling the skill's scripts from a justfile
Define the skill's location once and call its scripts through it, so the justfile works on any machine (`C64_DECOMP` overrides the default, which is the symlink Claude Code uses):
```
skill := env_var_or_default("C64_DECOMP", home_directory() / ".claude/skills/c64-decomp")
test:        python3 {{skill}}/scripts/sim/run_tests.py --root .
golden:      python3 {{skill}}/scripts/golden/golden.py check
golden-t:    python3 {{skill}}/scripts/golden/golden.py check-t
coverage:    python3 {{skill}}/scripts/coverage/run_scenarios.py
check:       just verify {{phase}}; just test {{phase}}; just golden {{phase}}     # see templates/justfile.in
```

## Recipe contract (roles, and the fallback when a project lacks one)
The skill and its agents refer to recipes by **role**, because projects do not all spell them the same (one has `assemble`, `verify`, `todos`, `p2todos`). Required: `default` (lists recipes) and a phase 1 gate named `verify`. Everything else is a role with a fallback:
| Role | Usual name | If the project has none |
|---|---|---|
| assemble, no diff | `build` (older name `experiment`, or `assemble`) | run `framework/scripts/build.sh` |
| phase 2 gate | `check` | run its parts: build phase 2, `scripts/raw_refs.py`, align check, the tests, the golden traces |
| tests | `test` | run the project's test runner directly |
| list TODO markers | `todo [tag]` (or `todos`, `p2todos`) | `grep -rn 'TODO(' phase*/src` |
| list sections | `sections` | `grep -rn 'SECTION:' phase*/src` |
| align comments | `align`, `align-check` | `scripts/align_comments.py` |
| run / smoke test | `launch`, `smoke` | start the emulator by hand with the symbol file |
| Ghidra sync state | `sync-state`, `synced` | skip, but never edit Ghidra and the source in both directions |
Shipped in `templates/justfile.in` (role `gfx`: `just gfx [ARGS]` renders the game graphics to `docs/gfx/`); shipped in `templates/justfile.in` (role `launch`, `smoke`): `launch` (builds, then `scripts/launcher/run_game.py`) and `smoke` (builds, then `scripts/launcher/smoke.py`); both are read from `project.config` (`LAUNCH_MODE`, `SMOKE_CYCLES`, `JUDGE_CROP` ...). Optional roles seen in practice (add where useful): `comment-check` (comment rules), `anon-check` (anonymous-label limits), `rawops` (the raw-address check; the skill's `raw_refs.py` does the same), `progress` (how much is classified). Docs-site recipes stay out of the skill.
A project that lacks a role-recipe the loop needs should add it (named as above) rather than rely on the fallback.

## The standard recipe set
Present in every project (names fixed so the skill and agents can rely on them). **Every build, check and run command takes the phase as its argument**: `just verify 1`, `just verify 2`; with no argument it uses `ACTIVE_PHASE` in `project.config` (1 until phase 2 starts, then 2: one line to change).
| Recipe | Meaning |
|---|---|
| `build [phase]` (alias `experiment`) | assemble a phase's source, no comparison; leaves `build/game.sym` (`build/p2/game.sym`) |
| `verify [phase]` | **the gate**: assemble and compare byte for byte with `reference/` (reports the first differing offset as a C64 address); phase 2 is byte-identical until the byte-changing removals |
| `launch [phase]` | run in VICE at real speed with symbols, as the hand-off left it |
| `smoke [phase]` | unattended boot in VICE (warp), screenshot, compared with `tools/smoke_ref.png` |
| `test [phase]` | routine tests (code run in the 6510 simulator against Python models) |
| `golden [phase]` | golden traces: phase 1 exact then timing-tolerant, phase 2 timing-tolerant; `golden-record` records on phase 1 |
| `check [phase]` | everything that must stay green: verify, (phase 2: raw-address and comment checks), test, golden |
| `reloc [phase]` / `fuzz-layout` | what would break if things moved / the relocation stress test |
| `sections` / `todo [tag]` | list section banners / TODO markers (by tag) |
| `align` / `comment-check` / `anon-check` | the source-tidiness checks |
| `slice-check` / `slice-start` / `slice-merge` | the checks of a slice, a scratch copy for an agent, taking its commits back (these use the active phase) |
| `sync-state` / `synced <dir>` | which of Ghidra and the source was last synced / record a sync |
Projects add their own (`gfx`, `build-disk`, `progress` ...). The skill's `scripts/` are called from recipes (for example `layout` -> `scripts/check_layout.py`).

## Check
At the time of writing only `default`, `launch` and `verify` exist in all three projects; `align`, `experiment`, `sections`, `smoke`, `sync-state`, `synced`, `todo` exist in two. Bringing each project to the standard set is that project's agent's job.
