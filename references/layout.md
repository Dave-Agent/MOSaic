# Project file layout (decided with the user 2026-10-29)

## The tree
```
project.config        the ONLY place project paths, names and addresses live (framework and skill scripts read it)
justfile              thin: imports framework/recipes.just, adds project recipes
README.md             what the project is, and exactly how to SUPPLY the original data and verify (see below)
CLAUDE.md             what is specific to this game; everything shared lives in the MOSaic skill

phase1/src/           the byte-identical monolith + label files (symbols, zero_page, variables, constants) + libs/
phase2/src/           the split source: game/ platform/ data/ + label files + libs/ (a main file that imports the rest)
libs/                 a copy of the skill's hardware libs (inside each phase's src/)
framework/            a copy of the skill's `framework/` master: generic build/verify/launch/Ghidra-import tooling (never edited in a project; no project values inside; `scripts/framework_sync.py` keeps it current)
tools/                project scripts; tools/migrations/ holds one-off rewrites that were applied (templates, not to re-run)
docs/                 analysis notes, the porting guide, generated lists
launcher/             hand-written, NOT game: whatever is needed to run the game in an emulator

originals/            media as downloaded: SHA-256 in originals.sha256 (committed), never attached to an emulator directly; read-only is optional (--protect)    NOT COMMITTED
dumps/                emulator RAM dumps                         NOT COMMITTED
reference/            the cleaned reference image (diff target)  NOT COMMITTED; reference.sha256 IS committed
build/ ghidra/ analysis/ extracted/   derived, regenerable      NOT COMMITTED
```

## Prefer not committing the game's binaries
**Prefer not committing any ROM, disk image, tape, cartridge, memory dump or image that is the original program's bytes, or a byte-for-byte derivation of it, unless we built it ourselves from our own source.** That covers `originals/`, `dumps/`, `reference/`, an unpacked or cleaned image, and tables generated from them. We do not own that data, and a public repository must not redistribute it.
- **Commit instead:** the source, the tools that derive the reference from the original (`make_reference.py` or equivalent), a **checksum file** (`reference.sha256`) that proves a supplied image is the right one, and the README steps to supply it (which release, where it came from, which file name, which hash).
- **`.gitignore` lists** `/originals/`, `/dumps/`, `/reference/`, `/build/`, `/ghidra/`, `/analysis/`, `/extracted/`, any stray `/*.prg`, `__pycache__/`, `.claude/settings.local.json`, tool state (`progress.db`, `.sync-state`), editor noise, and Kick's working copies next to the source.
- **Our own built output is also not committed** (`build/`): it is derived from the source. The exception is a small binary we wrote by hand (for example a launcher stub) when it cannot be rebuilt from text.
- **A missing original fails clearly.** `just verify` and every test that needs the reference say which file is missing, the expected checksum and where the README explains it; they do not silently skip. Tests that need no original data run without it.
- **History:** a binary that is already in git history stays there until the history is rewritten, which is an outward-facing change (forks, clones, a public mirror). Do not rewrite it without the user's explicit decision per project; stop committing it going forward first.

## README: supplying the data
Name the game and release, the file(s) needed, the checksum, where the user puts them, and the one command that derives `reference/` and verifies it. Anyone cloning the repo can then reproduce the build from their own copy.

## Mirrors
A public mirror, if any, is one-way: edit `phase1/` or `phase2/`, commit, publish; never edit the mirror. It contains source only, under the same rule.

## Check
`scripts/check_layout.py` lists tracked files that look like game binaries (by extension and path), checks that `.gitignore` covers the derived and supplied directories, that a `reference.sha256` is present when `reference/` exists, and that the README mentions supplying the data. Add `COMMIT_BINARIES="path path"` to `project.config` for hand-made binaries that are meant to be tracked.
