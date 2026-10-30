#!/usr/bin/env bash
# MOSaic setup: checks your tools, links the skill into Claude Code, and (if you want) creates a project for a game.
#
#   ./setup.sh                      ask the questions
#   ./setup.sh --check              only check the tools
#   ./setup.sh --link               link the skill and check the tools, no questions, no project
#   ./setup.sh --root DIR --name "Game Name" --media FILE     no questions: create the project
#
# It changes only: the link ~/.claude/skills/mosaic, and the project folder you name. Nothing is installed for you.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"
LINK="$SKILLS_DIR/mosaic"
MODE_CHECK=0; LINK_ONLY=0; ROOT=""; NAME=""; MEDIA=""
while [ $# -gt 0 ]; do
    case "$1" in
        --check) MODE_CHECK=1 ;;
        --link)  LINK_ONLY=1 ;;
        --root)  ROOT="${2:-}"; shift ;;
        --name)  NAME="${2:-}"; shift ;;
        --media) MEDIA="${2:-}"; shift ;;
        -h|--help) sed -n '2,/^set -e/{/^set -e/!p}' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1 (try --help)"; exit 2 ;;
    esac
    shift
done

say()  { printf '\n%s\n' "$*"; }
ask()  {   # ask "question" default(y|n) -> returns 0 for yes
    local q="$1" d="${2:-y}" a hint="[Y/n]"; [ "$d" = n ] && hint="[y/N]"
    if [ ! -t 0 ] && [ -z "${MOSAIC_ASSUME_STDIN:-}" ]; then [ "$d" = y ]; return; fi
    read -r -p "$q $hint " a || a=""; a="${a:-$d}"; case "$a" in [Yy]*) return 0 ;; *) return 1 ;; esac
}
prompt() { local q="$1" def="${2:-}" a; if [ -n "$def" ]; then read -r -p "$q [$def] " a || a=""; echo "${a:-$def}"; else read -r -p "$q " a || a=""; echo "$a"; fi; }
expand() { local p="$1"; echo "${p/#\~/$HOME}"; }

say "MOSaic setup"
echo "Skill folder: $HERE"

# ---- 1. Python (everything else runs through it)
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is not installed. Install it with your package manager (for example: sudo apt install python3), then run this again."
    exit 1
fi

# ---- 2. Link the skill so Claude Code can find it
say "Step 1 of 3: link the skill into Claude Code"
mkdir -p "$SKILLS_DIR"
if [ -L "$LINK" ] && [ "$(readlink -f "$LINK")" = "$(readlink -f "$HERE")" ]; then
    echo "ok: $LINK already points here."
elif [ -e "$LINK" ] || [ -L "$LINK" ]; then
    echo "$LINK already exists and points to: $(readlink -f "$LINK" 2>/dev/null || echo '(not a link)')"
    if [ "$MODE_CHECK" = 1 ]; then echo "(--check: leaving it)"; elif ask "Replace it with a link to this folder?" n; then rm -f "$LINK"; ln -s "$HERE" "$LINK"; echo "linked: $LINK -> $HERE"; else echo "left as it was."; fi
elif [ "$MODE_CHECK" = 1 ]; then
    echo "not linked yet: $LINK (run ./setup.sh without --check to create it)"
else
    ln -s "$HERE" "$LINK"; echo "linked: $LINK -> $HERE"
fi

# ---- 3. Check the tools
say "Step 2 of 3: check your tools"
if python3 "$HERE/scripts/check_env.py" --brief --role run --role trace --role ghidra; then TOOLS_OK=1; else TOOLS_OK=0; fi
if [ "$TOOLS_OK" = 0 ]; then
    echo
    echo "Some required tools are missing (marked MISSING above, each with how to get it). Install them and run ./setup.sh again."
    echo "Kick Assembler: download it from http://theweb.dk/KickAssembler/ and put KickAss.jar in ~/tools/ ."
    echo "Ghidra: download it from https://ghidra-sre.org and unzip it in your home folder."
    [ "$MODE_CHECK" = 1 ] || [ "$LINK_ONLY" = 1 ] && exit 1
    ask "Carry on and create a project anyway?" n || exit 1
fi
{ [ "$MODE_CHECK" = 1 ] || [ "$LINK_ONLY" = 1 ]; } && { echo; echo "Tools OK."; exit 0; }

# ---- 4. A project for a game
say "Step 3 of 3: create a project for a game"
if [ -z "$ROOT$NAME$MEDIA" ]; then ask "Create a project now?" y || { echo; echo "Done. To make a project later: ./setup.sh"; exit 0; }; fi

if [ -z "$MEDIA" ]; then
    echo "The game's disk or tape file ends in .d64, .g64 or .tap (a copy with the copy protection removed is best)."
    while :; do
        MEDIA="$(expand "$(prompt "Path to the game file:")")"
        [ -f "$MEDIA" ] && break
        echo "  no such file: $MEDIA"
    done
else MEDIA="$(expand "$MEDIA")"; [ -f "$MEDIA" ] || { echo "no such file: $MEDIA"; exit 1; }; fi
case "${MEDIA,,}" in
    *.d64|*.g64|*.d71|*.d81|*.tap|*.t64|*.prg) ;;
    *.crt) echo "  note: cartridge images are not handled by MOSaic yet; continuing anyway." ;;
    *) echo "  note: unusual file type; continuing anyway." ;;
esac

if [ -z "$NAME" ]; then NAME="$(prompt "Game name:" "$(basename "${MEDIA%.*}" | tr '_' ' ')")"; fi
SLUG="$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-' | sed 's/--*/-/g; s/^-//; s/-$//')"
if [ -z "$ROOT" ]; then ROOT="$(prompt "Project folder:" "~/C64Projects/$SLUG")"; fi
ROOT="$(expand "$ROOT")"

echo
echo "About to create:"
echo "  game:     $NAME"
echo "  file:     $MEDIA   (copied into the project; yours is not touched)"
echo "  project:  $ROOT"
if [ -z "${MOSAIC_YES:-}" ] && ! ask "Go ahead?" y; then echo "Cancelled."; exit 0; fi

python3 "$HERE/scripts/new_project.py" --no-next --root "$ROOT" --name "$NAME" --media "$MEDIA"

if command -v just >/dev/null 2>&1; then
    say "Where the new project stands"
    (cd "$ROOT" && just status 2>&1 | sed -n '/^NEXT/,/see:/p') || true
else
    echo
    echo "'just' is not installed, so the project commands (just status, just verify ...) will not work yet: https://github.com/casey/just"
fi

say "Done. Next:"
echo "  1. cd \"$ROOT\""
echo "  2. Open Claude Code there and say:"
echo "       Use the MOSaic skill. Do HOWTO step 2: create a source that builds and starts this game, without stopping between its parts."
echo "  3. Afterwards, \"move to the next stage\" does the next step. The full guide is $HERE/HOWTO.md"
