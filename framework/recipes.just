# framework/recipes.just
# Generic recipes. Imported by the thin root justfile. All logic lives here and
# in framework/scripts; nothing project-specific. project.config supplies the
# specifics. Next project imports this same file unchanged.

# PROJECT_ROOT is exported so the scripts resolve paths from the project root
# regardless of where just is invoked.
export PROJECT_ROOT := justfile_directory()

# Assemble canonical source and diff against the reference PRG. The gate.
verify:
    bash framework/scripts/verify.sh

# Assemble current working source, no diff, for fast iteration.
experiment:
    PROJECT_ROOT="{{justfile_directory()}}" bash framework/scripts/build.sh

# Experiment-build then launch emulator with symbols. target=vice|retro (default vice).
# Optional pokes JSON patches a binary copy before launch: just launch vice pokes/example.json
launch target="vice" pokes="":
    bash framework/scripts/launch.sh {{target}} {{pokes}}

# List section banners in the phase 1 source (SECTION: tags; see framework/conventions).
sections:
    #!/usr/bin/env bash
    source project.config
    grep -n 'SECTION:' "$SRC_MAIN" || echo "no sections yet"

# List sections still marked unknown.
todo:
    #!/usr/bin/env bash
    source project.config
    grep -n 'STATUS:  unknown' "$SRC_MAIN" || echo "no unknown sections"

# Show which side last won the sync, so you never sync the wrong direction.
sync-state:
    @cat "{{justfile_directory()}}/.sync-state" 2>/dev/null || echo "no sync recorded yet"

# Record a sync direction. Usage: just synced ghidra-to-source
synced direction:
    @echo "LAST_SYNC: {{direction}} @ $(date -Iseconds)" > "{{justfile_directory()}}/.sync-state"
    @echo "recorded: {{direction}}"

# Commit everything with the project's trailers (COMMIT_TRAILERS in project.config, lines separated by \n). Usage: just commit "message"
commit $msg:
    #!/usr/bin/env bash
    set -euo pipefail
    . ./project.config
    git add -A
    if [ -n "${COMMIT_TRAILERS:-}" ]; then
        git commit -q -m "$msg" -m "$(printf '%b' "$COMMIT_TRAILERS")"
    else
        git commit -q -m "$msg"
    fi
    git log -1 --oneline

# Align the // comment columns of the phase 1 source (whitespace only; run verify after).
align:
    python3 {{env_var_or_default("C64_DECOMP", home_directory() / ".claude/skills/c64-decomp")}}/scripts/align_comments.py --root . --phase 1 --write
