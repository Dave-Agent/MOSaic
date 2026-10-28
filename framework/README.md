# framework/

Generic C64 reverse-engineering tooling. Nothing here is specific to any one
project; all specifics come from `../project.config`, which the scripts source.

This subtree is kept extraction-clean by one rule: **no project-specific value
ever lives in here.** Once proven on the first project, it lifts out into its
own repo with minimal change.

## Pieces

- `recipes.just` — the `verify` / `experiment` / `launch` / `sections` / `todo`
  / sync recipes. Imported by the project's thin root `justfile`.
- `scripts/build.sh` — KickAssembler invocation, config-driven. Emits PRG plus
  VICE symbol file and KickAss debug file.
- `scripts/verify.sh` — assembles canonical source and diffs against the
  reference PRG, reporting the first diverging offset as a C64 address.
- `scripts/launch.sh` — experiment-build then into RetroDebugger or VICE with
  symbols loaded.
- `ghidra/import_symbols.py` — source->Ghidra bridge. Reads KickAssembler's VICE
  symbol output and applies labels/comments to the open Ghidra program.
  Re-runnable and overwriting.
- `conventions/section-marker.md` — the byte-neutral section-banner format for
  landmarking the monolith and pre-staging the phase-2 split.

## Reusing on the next project

Copy `framework/` into the new project, write a new `project.config`, add the
thin root `justfile` that imports `framework/recipes.just`. No edits to anything
under `framework/`.

## The config contract

Every script begins by sourcing `project.config` from the project root. The keys
it relies on: `JAVA`, `KICKASS_JAR`, `SRC_MAIN`, `OUTPUT_PRG`, `VICE_SYMBOLS`,
`DEBUG_FILE`, `REFERENCE_PRG`, `LOAD_ADDRESS`, `IGNORE_LOAD_ADDRESS`,
`BUILD_DIR`, `VICE_BIN`, `RETRODEBUGGER_BIN`. Add keys here as the framework
grows; never inline a specific value.
