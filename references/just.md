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
check:       build-phase2 test golden-t     # plus the raw-address and align checks
```

## Recipe contract (roles, and the fallback when a project lacks one)
The skill and its agents refer to recipes by **role**, because projects do not all spell them the same (one has `assemble`, `verify`, `todos`, `p2todos`). Required: `default` (lists recipes) and a phase 1 gate named `verify`. Everything else is a role with a fallback:
| Role | Usual name | If the project has none |
|---|---|---|
| assemble, no diff | `experiment` (or `assemble`) | run `framework/scripts/build.sh` |
| phase 2 gate | `check` | run its parts: build phase 2, `scripts/raw_refs.py`, align check, the tests, the golden traces |
| tests | `test` | run the project's test runner directly |
| list TODO markers | `todo [tag]` (or `todos`, `p2todos`) | `grep -rn 'TODO(' phase*/src` |
| list sections | `sections` | `grep -rn 'SECTION:' phase*/src` |
| align comments | `align`, `align-check` | `scripts/align_comments.py` |
| run / smoke test | `launch`, `smoke` | start the emulator by hand with the symbol file |
| Ghidra sync state | `sync-state`, `synced` | skip, but never edit Ghidra and the source in both directions |
Optional roles seen in practice (add where useful): `comment-check` (comment rules), `anon-check` (anonymous-label limits), `rawops` (the raw-address check; the skill's `raw_refs.py` does the same), `progress` (how much is classified). Docs-site recipes stay out of the skill.
A project that lacks a role-recipe the loop needs should add it (named as above) rather than rely on the fallback.

## The standard recipe set
Present in every project (names fixed so the skill and agents can rely on them):
| Recipe | Meaning |
|---|---|
| `verify` | assemble the canonical source and diff against `reference/`; the phase 1 gate (reports the first differing offset as a C64 address) |
| `experiment` | assemble the working source, no diff; fast iteration |
| `check` | the phase 2 gate: build, raw-address check, alignment, routine tests, golden traces |
| `test` | routine tests (code run in a simulator against models) |
| `sections` / `todo [tag]` | list section banners / regions still unknown and TODO markers (by tag) |
| `align` / `align-check` | align `//` comments to the project's column / fail if not aligned |
| `launch` / `smoke` | run in an emulator with symbols / unattended boot and screenshot judge |
| `sync-state` / `synced <dir>` | which of Ghidra and the source was last synced / record a sync |
Projects add their own (`golden`, `fuzz-layout`, `reloc`, `build-disk`, `comment-check`, `progress` ...). The skill's `scripts/` are called from recipes (for example `check-layout` -> `scripts/check_layout.py`).

## Check
At the time of writing only `default`, `launch` and `verify` exist in all three projects; `align`, `experiment`, `sections`, `smoke`, `sync-state`, `synced`, `todo` exist in two. Bringing each project to the standard set is that project's agent's job.
